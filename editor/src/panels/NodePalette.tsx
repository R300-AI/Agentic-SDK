import { NODE_DISPLAY_ORDER } from "../types";

interface Props {
  onDownload: () => void;
  onLoad: (yaml: string) => void;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function NodePalette({ onDownload, onLoad, selectedId, onSelect }: Props) {
  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result ?? "");
      onLoad(text);
    };
    reader.readAsText(file, "utf-8");
    e.target.value = ""; // 允許再次選同一個檔
  };

  return (
    <aside className="palette">
      <h3>節點</h3>
      <ul className="palette-list">
        {NODE_DISPLAY_ORDER.map((name) => (
          <li
            key={name}
            className={selectedId === name ? "palette-item selected" : "palette-item"}
            onClick={() => onSelect(name)}
          >
            {name}
          </li>
        ))}
      </ul>
      <hr />
      <h3>YAML</h3>
      <button onClick={onDownload}>下載 YAML</button>
      <label className="file-button">
        載入 YAML
        <input type="file" accept=".yaml,.yml" onChange={handleFile} />
      </label>
    </aside>
  );
}
