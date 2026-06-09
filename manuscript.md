# 1. 起 Gemma3 上游
conda activate ryzen-ai-1.7.1
cd <amd-ryzen-ai-benchmark>
python api.py --model gemma3-4b-npu

# 2. clone / pull Agentic SDK 最新版
git clone https://github.com/<your-org>/Agentic-SDK.git   # 或 git pull
cd Agentic-SDK
git submodule update --init
uv sync --extra dev
Copy-Item .env.example .env
# 編輯 .env 填 AZURE_FOUNDRY_ENDPOINT / AZURE_FOUNDRY_API_KEY / AZURE_FOUNDRY_DEPLOYMENT

# 3. 跑多基台 demo
uv run python scripts\demo_multi_backend.py "請用一句話自我介紹"

```gemma 3 npu terminal
INFO:     127.0.0.1:54127 - "POST /v1/chat/completions HTTP/1.1" 500 Internal Server Error
ERROR:    Exception in ASGI application
Traceback (most recent call last):
  File "C:\Users\eosl1\anaconda3\envs\ryzen-ai-1.7.1\Lib\site-packages\uvicorn\protocols\http\h11_impl.py", line 415, in run_asgi
    result = await app(  # type: ignore[func-returns-value]
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\eosl1\anaconda3\envs\ryzen-ai-1.7.1\Lib\site-packages\uvicorn\middleware\proxy_headers.py", line 56, in __call__
    return await self.app(scope, receive, send)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\eosl1\anaconda3\envs\ryzen-ai-1.7.1\Lib\site-packages\fastapi\applications.py", line 1159, in __call__
    await super().__call__(scope, receive, send)
  File "C:\Users\eosl1\anaconda3\envs\ryzen-ai-1.7.1\Lib\site-packages\starlette\applications.py", line 90, in __call__
    await self.middleware_stack(scope, receive, send)
  File "C:\Users\eosl1\anaconda3\envs\ryzen-ai-1.7.1\Lib\site-packages\starlette\middleware\errors.py", line 186, in __call__
    raise exc
  File "C:\Users\eosl1\anaconda3\envs\ryzen-ai-1.7.1\Lib\site-packages\starlette\middleware\errors.py", line 164, in __call__
    await self.app(scope, receive, _send)
  File "C:\Users\eosl1\anaconda3\envs\ryzen-ai-1.7.1\Lib\site-packages\starlette\middleware\exceptions.py", line 63, in __call__
    await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
  File "C:\Users\eosl1\anaconda3\envs\ryzen-ai-1.7.1\Lib\site-packages\starlette\_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "C:\Users\eosl1\anaconda3\envs\ryzen-ai-1.7.1\Lib\site-packages\starlette\_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "C:\Users\eosl1\anaconda3\envs\ryzen-ai-1.7.1\Lib\site-packages\fastapi\middleware\asyncexitstack.py", line 18, in __call__
    await self.app(scope, receive, send)
  File "C:\Users\eosl1\anaconda3\envs\ryzen-ai-1.7.1\Lib\site-packages\starlette\routing.py", line 660, in __call__
    await self.middleware_stack(scope, receive, send)
  File "C:\Users\eosl1\anaconda3\envs\ryzen-ai-1.7.1\Lib\site-packages\starlette\routing.py", line 680, in app
    await route.handle(scope, receive, send)
  File "C:\Users\eosl1\anaconda3\envs\ryzen-ai-1.7.1\Lib\site-packages\starlette\routing.py", line 276, in handle
    await self.app(scope, receive, send)
  File "C:\Users\eosl1\anaconda3\envs\ryzen-ai-1.7.1\Lib\site-packages\fastapi\routing.py", line 134, in app
    await wrap_app_handling_exceptions(app, request)(scope, receive, send)
  File "C:\Users\eosl1\anaconda3\envs\ryzen-ai-1.7.1\Lib\site-packages\starlette\_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "C:\Users\eosl1\anaconda3\envs\ryzen-ai-1.7.1\Lib\site-packages\starlette\_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "C:\Users\eosl1\anaconda3\envs\ryzen-ai-1.7.1\Lib\site-packages\fastapi\routing.py", line 120, in app
    response = await f(request)
               ^^^^^^^^^^^^^^^^
  File "C:\Users\eosl1\anaconda3\envs\ryzen-ai-1.7.1\Lib\site-packages\fastapi\routing.py", line 674, in app
    raw_response = await run_endpoint_function(
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\eosl1\anaconda3\envs\ryzen-ai-1.7.1\Lib\site-packages\fastapi\routing.py", line 328, in run_endpoint_function
    return await dependant.call(**values)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\eosl1\amd-ryzen-ai-benchmark\api.py", line 135, in chat_completions
    _build_response("".join(tokens), request.model)
                    ^^^^^^^^^^^^^^^
  File "C:\Users\eosl1\amd-ryzen-ai-benchmark\ryzenai\modules\gemma3_4b_npu.py", line 38, in generate
    prompt = _apply_chat_template(self._model_dir, self._tokenizer, messages)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\eosl1\amd-ryzen-ai-benchmark\ryzenai\modules\gemma3_4b_npu.py", line 130, in _apply_chat_template
    return tokenizer.apply_chat_template(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
RuntimeError: Conversation roles must alternate user/assistant/user/assistant/... at row 19, column 27:
    {%- if (message['role'] == 'user') != (loop.index0 % 2 == 0) -%}
        {{ raise_exception("Conversation roles must alternate user/assistant/user/assistant/...") }}
                          ^
    {%- endif -%}
 at row 19, column 9:
    {%- if (message['role'] == 'user') != (loop.index0 % 2 == 0) -%}
        {{ raise_exception("Conversation roles must alternate user/assistant/user/assistant/...") }}
        ^
    {%- endif -%}
 at row 18, column 69:
{%- for message in loop_messages -%}
    {%- if (message['role'] == 'user') != (loop.index0 % 2 == 0) -%}
                                                                    ^
        {{ raise_exception("Conversation roles must alternate user/assistant/user/assistant/...") }}
 at row 18, column 5:
{%- for message in loop_messages -%}
    {%- if (message['role'] == 'user') != (loop.index0 % 2 == 0) -%}
    ^
        {{ raise_exception("Conversation roles must alternate user/assistant/user/assistant/...") }}
 at row 17, column 37:
{%- endif -%}
{%- for message in loop_messages -%}
                                    ^
    {%- if (message['role'] == 'user') != (loop.index0 % 2 == 0) -%}
 at row 17, column 1:
{%- endif -%}
{%- for message in loop_messages -%}
^
    {%- if (message['role'] == 'user') != (loop.index0 % 2 == 0) -%}
 at row 1, column 1:
{{ bos_token }}
^
{%- if messages[0]['role'] == 'system' -%}
```

# 4. 推結果回來給我看