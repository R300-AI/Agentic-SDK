/**
 * Talking to a voice agent from the page: microphone in, answer out.
 *
 * The page never holds a credential. It opens one websocket to the Playground
 * and everything — the transcription service, the synthesis service — happens
 * on the other side of it.
 *
 * Interruption is handled here first and reported afterwards. Stopping the
 * playback is a local decision the browser can make in one frame; truncating
 * the conversation is the server's job and can take as long as it takes. Doing
 * them in the other order would leave the agent talking over the person for a
 * whole round trip, which is the thing being interrupted is meant to fix.
 */

const TRANSCRIBE_SAMPLE_RATE = 16000;
const SYNTHESIS_SAMPLE_RATE = 24000;
const FRAME_SAMPLES = 1024;

const SPECTRUM_BANDS = 14;

export function bindVoiceConversation(page, { onTranscript, onStatus, onState, onSpectrum, onCutOffAfterTheRun }) {
	if (page?.dataset.voice !== "true") {
		return null;
	}
	// Wanting to hear the answer is not wanting to be listened to. An agent
	// that only speaks opens the connection to play through and never asks for
	// a microphone.
	const listens = page.dataset.voiceInput === "true";
	const session = {
		id: `voice-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
		socket: null,
		context: null,
		playing: [],
		playheadAt: 0,
		startedSpeakingAt: 0,
		paused: false,
		listenAnalyser: null,
		speakAnalyser: null,
		carry: new Uint8Array(0),
	};

	const say = (message) => onStatus?.(message);
	const enter = (state, detail) => {
		if (session.paused && state !== "paused") {
			// Only resume() leaves a pause. Anything else — a late reply, an
			// answer finishing — would put the microphone back without the
			// person asking, while they are halfway through typing.
			return;
		}
		// One place decides what the page is showing, because a voice agent
		// with no visible state is indistinguishable from one that is broken:
		// the person talks, nothing happens, and nothing says why.
		onState?.(state, detail);
	};

	function open() {
		const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
		const socket = new WebSocket(`${scheme}//${window.location.host}/playground/voice/${session.id}`);
		socket.binaryType = "arraybuffer";
		socket.addEventListener("message", (event) => {
			if (typeof event.data !== "string") {
				play(event.data);
				return;
			}
			handle(JSON.parse(event.data));
		});
		socket.addEventListener("close", () => enter("closed"));
		session.socket = socket;
	}

	function handle(message) {
		if (session.paused && (message.type === "speech_started" || message.type === "transcript")) {
			// Audio already in flight when the microphone was paused. Acting on
			// it would start a turn the person did not ask for, from the middle
			// of a sentence they abandoned.
			return;
		}
		if (message.type === "speech_started") {
			// The service heard someone begin, before it knows what they said.
			const wasSpeaking = session.playing.length > 0;
			stopPlaying();
			enter(wasSpeaking ? "interrupted" : "listening");
			return;
		}
		if (message.type === "transcript" && message.text) {
			enter("heard", message.text);
			onTranscript?.(message.text);
			return;
		}
		if (message.type === "spoken") {
			if (!session.playing.length) {
				enter("listening");
			}
			return;
		}
		if (message.type === "nothing_to_interrupt") {
			// Speaking takes far longer than answering, so by the time someone
			// talks over the tail of an answer the run is usually finished and
			// the whole of it is already in the conversation. Nothing on the
			// server knows how much was played; this page does, and says so.
			onCutOffAfterTheRun?.(message.heard_seconds);
			return;
		}
		if (message.type === "unavailable") {
			enter("unavailable", message.message);
			say(message.message);
			return;
		}
		if (message.type === "nothing_to_interrupt") {
			say(message.message);
		}
	}

	async function listen() {
		let microphone;
		try {
			microphone = await navigator.mediaDevices.getUserMedia({
				audio: {
					// 它自己的聲音會被語音偵測當成有人插話：把這個 Agent 合成的
					// 回答當成麥克風輸入送進去，音量降到 15% 仍然觸發。瀏覽器的
					// 回音消除是第一層防禦，而規範上這三項是請求不是保證，所以
					// 要求之後還要看一次實際拿到什麼。
					echoCancellation: true,
					noiseSuppression: true,
					autoGainControl: true,
				},
			});
		} catch (error) {
			// A refusal and a missing microphone look the same from here: in both
			// cases the page would otherwise just sit there being silent.
			enter("denied");
			say("這個 Agent 要用麥克風才能聽你說話。請在瀏覽器的網址列允許麥克風權限，然後重新整理頁面。你也可以直接打字。");
			return;
		}
		const applied = microphone.getAudioTracks()[0]?.getSettings?.() || {};
		if (applied.echoCancellation !== true) {
			// 沒有回音消除時，開擴音會讓它把自己的聲音當成你在說話。講出來，
			// 否則使用者看到的是它莫名其妙自己停住。
			say("這台裝置沒有回音消除，開擴音時它可能把自己的聲音當成你在說話。建議戴耳機。");
		}
		open();
		const context = new AudioContext();
		session.context = context;
		// Browsers start an AudioContext suspended until the page has had a
		// user gesture. Granting microphone permission usually counts as one,
		// but not always, and a suspended context produces no audio events at
		// all — the page looks like it is listening and hears nothing.
		if (context.state === "suspended") {
			await context.resume().catch(() => {});
		}
		if (context.state !== "running") {
			say("瀏覽器還沒允許這個頁面播放與擷取聲音。點一下頁面任何地方就可以開始說話。");
			document.addEventListener("click", () => context.resume(), { once: true });
		}
		const source = context.createMediaStreamSource(microphone);
		session.listenAnalyser = analyserFor(context);
		source.connect(session.listenAnalyser);
		// An analyser with nothing downstream is never pulled, so it reports
		// silence for ever. A gain of zero gives it somewhere to go without
		// putting the microphone through the speakers.
		const silent = context.createGain();
		silent.gain.value = 0;
		session.listenAnalyser.connect(silent);
		silent.connect(context.destination);
		// Watching the frequencies rather than one loudness number, because a
		// bar that only rises and falls says "a sound happened" while a
		// spectrum says "your voice is what I am hearing".
		watchSpectrum();
		const meter = context.createScriptProcessor(FRAME_SAMPLES, 1, 1);
		meter.addEventListener("audioprocess", (event) => {
			send(event.inputBuffer.getChannelData(0), context.sampleRate);
		});
		source.connect(meter);
		meter.connect(context.destination);
		enter("listening");
	}

	function send(samples, sampleRate) {
		if (session.paused || session.socket?.readyState !== WebSocket.OPEN) {
			return;
		}
		session.socket.send(toServiceAudio(samples, sampleRate));
	}

	function watchSpectrum() {
		// Whichever end is making sound: the agent's own voice while it answers,
		// the person's while it listens. Advanced voice modes do the same, and
		// it is the difference between a decoration and a display.
		const analyser = session.playing.length ? session.speakAnalyser : session.listenAnalyser;
		onSpectrum?.(analyser ? bandsOf(analyser) : new Array(SPECTRUM_BANDS).fill(0));
		requestAnimationFrame(watchSpectrum);
	}

	function pause() {
		// Typing and talking must never both be live: two inputs racing produce
		// two turns for one question, and the person sees the agent answer
		// something they were still in the middle of saying.
		session.paused = true;
		stopPlaying();
		enter("paused");
	}

	function resume() {
		session.paused = false;
		session.carry = new Uint8Array(0);
		enter("listening");
	}

	function play(audio) {
		// An agent that only speaks has no microphone and so no context yet.
		if (!session.context) {
			session.context = new AudioContext();
		}
		const context = session.context;
		// Paused means paused in both directions. An answer that keeps talking
		// after someone switched to the keyboard is the agent ignoring them.
		if (!context || session.paused) {
			return;
		}
		// A frame off the socket is a slice of a stream, not a whole number of
		// samples: an odd byte length is normal, and the leftover byte is the
		// first half of a sample whose other half is in the next frame.
		const arrived = new Uint8Array(audio);
		const joined = new Uint8Array(session.carry.length + arrived.length);
		joined.set(session.carry);
		joined.set(arrived, session.carry.length);
		const whole = joined.length - (joined.length % 2);
		session.carry = joined.slice(whole);
		if (!whole) {
			return;
		}
		const samples = new Int16Array(joined.buffer.slice(0, whole));
		// Synthesis and transcription are different services at different
		// rates. Playing 24 kHz audio as 16 kHz stretches it by half again —
		// and stretches the heard duration reported back with it.
		const buffer = context.createBuffer(1, samples.length, SYNTHESIS_SAMPLE_RATE);
		const channel = buffer.getChannelData(0);
		for (let index = 0; index < samples.length; index += 1) {
			channel[index] = samples[index] / 32768;
		}
		const piece = context.createBufferSource();
		piece.buffer = buffer;
		if (!session.speakAnalyser) {
			session.speakAnalyser = analyserFor(context);
			session.speakAnalyser.connect(context.destination);
		}
		piece.connect(session.speakAnalyser);
		// Queued against the running clock rather than played on arrival, so the
		// pieces join up instead of overlapping each other.
		const startAt = Math.max(context.currentTime, session.playheadAt);
		if (!session.playing.length) {
			session.startedSpeakingAt = startAt;
			enter("speaking");
		}
		piece.start(startAt);
		session.playheadAt = startAt + buffer.duration;
		session.playing.push(piece);
		piece.addEventListener("ended", () => {
			session.playing = session.playing.filter((item) => item !== piece);
		});
	}

	function stopPlaying() {
		if (!session.playing.length) {
			return;
		}
		// How much of the answer the person actually heard — which only the thing
		// playing it knows, because speech lags generation by seconds.
		const heard = Math.max(0, (session.context?.currentTime || 0) - session.startedSpeakingAt);
		for (const piece of session.playing) {
			piece.stop();
		}
		session.playing = [];
		session.playheadAt = 0;
		session.carry = new Uint8Array(0);
		session.socket?.send(JSON.stringify({ type: "interject", heard_seconds: heard }));
	}

	if (listens) {
		// No button: a voice agent that has to be switched on is a form with a
		// microphone attached.
		listen();
	} else {
		open();
	}

	return { sessionId: session.id, pause, resume, enter };
}

function analyserFor(context) {
	const analyser = context.createAnalyser();
	// Small transform, heavily smoothed: this is a thing to glance at, not a
	// measurement, and an unsmoothed spectrum flickers into noise.
	analyser.fftSize = 128;
	analyser.smoothingTimeConstant = 0.75;
	return analyser;
}

/** The spectrum folded down to the handful of bars the page draws. */
export function bandsOf(analyser) {
	const bins = new Uint8Array(analyser.frequencyBinCount);
	analyser.getByteFrequencyData(bins);
	// Only the lower half: speech lives there, and the top of the range is
	// empty most of the time, which would leave half the bars permanently flat.
	const usable = Math.floor(bins.length / 2);
	const perBand = Math.max(1, Math.floor(usable / SPECTRUM_BANDS));
	const bands = [];
	for (let band = 0; band < SPECTRUM_BANDS; band += 1) {
		let total = 0;
		for (let offset = 0; offset < perBand; offset += 1) {
			total += bins[band * perBand + offset] || 0;
		}
		bands.push(total / perBand / 255);
	}
	return bands;
}

/** Resample to the rate the transcription service takes, as 16-bit mono. */
export function toServiceAudio(samples, sampleRate) {
	const ratio = sampleRate / TRANSCRIBE_SAMPLE_RATE;
	const length = Math.floor(samples.length / ratio);
	const out = new Int16Array(length);
	for (let index = 0; index < length; index += 1) {
		const value = samples[Math.floor(index * ratio)];
		// Clamped before scaling: a value outside ±1 wraps around when it is
		// truncated, and a loud word comes out as a crackle.
		const clamped = Math.max(-1, Math.min(1, value));
		out[index] = clamped < 0 ? clamped * 32768 : clamped * 32767;
	}
	return out.buffer;
}
