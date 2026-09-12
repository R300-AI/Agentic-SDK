# 技能包

技能包是一疊寫給模型照著做的作業說明。一個技能包裝著數個技能，每個技能是一份 `SKILL.md` 加上它用到的補充檔案。規劃模組掛上技能包之後，某一輪需要照某套流程做事時，就把那個技能的內容逐字加進對話。

技能屬於規劃模組，不屬於流程：`Workflow` 不知道技能存在，其他四類模組也不必更動。這個歸屬的來由見 [ADR 0006](../adr/0006-skills-belong-to-the-planning-module.md)，技能包的組成決定見 [ADR 0004](../adr/0004-what-a-skill-package-is-made-of.md)。

## 資料夾長什麼樣

```
meeting-notes/
├── package.yaml
├── skills/
│   ├── minutes/
│   │   └── SKILL.md
│   └── action-items/
│       └── SKILL.md
├── instructions/
│   └── checklist.md
└── prompts/
    └── format.md
```

`skills/` 底下一個資料夾就是一個技能，資料夾名稱即技能名稱。`instructions/` 與 `prompts/` 放技能引用的補充檔案，同一份檔案可以被多個技能引用。

## SKILL.md

開頭是 YAML frontmatter，欄位沿用開放的 Agent Skills 格式，必填的是 `name` 與 `description`；`name` 要與資料夾名稱相同。`description` 是規劃模組挑技能時唯一讀到的線索，寫這個技能什麼時候該用。

```markdown
---
name: minutes
description: 把逐字稿整理成會議紀錄，輸出固定格式的會議資訊與決議事項
---

先確認會議主題與出席者，再逐段標出決議。
```

frontmatter 以下是技能本體，會逐字進到對話。

## package.yaml

對應檔記錄每個技能用到哪些補充檔案，以及順序。技能取用時，內容依序是本體、`instructions`、`prompts`。

```yaml
skills:
  minutes:
    instructions: [checklist.md]
    prompts: [format.md]
  action-items:
    instructions: []
    prompts: []
    disable-model-invocation: true
```

`disable-model-invocation: true` 的技能不列進給模型看的清單，只有使用者用 `/名稱` 指名時才取用。這個宣告寫在對應檔而不是 `SKILL.md`，因此 `SKILL.md` 只保留開放格式定義的欄位，別的工具寫的技能可以原封不動掛上來。

## 檢查規則

掛載時逐條檢查，違反任何一條就整包拒絕，並指出是哪一條、哪一個檔案。

| 規則 | 什麼情況會被拒絕 |
| --- | --- |
| `missing_frontmatter` | `SKILL.md` 開頭沒有寫出名稱與說明。 |
| `name_mismatch` | 資料夾名稱、`SKILL.md` 的 `name` 與對應檔條目三者不一致。 |
| `name_taken` | 這個 agent 已經掛了同名技能。 |
| `description_too_long` | 說明超過 1,024 字元。 |
| `too_large` | 單一技能加進對話的內容超過上限（預設 20,000 字元）。 |
| `invalid_mapping` | 對應檔不是合法 YAML，或技能條目的格式不對。 |
| `invalid_declaration` | `disable-model-invocation` 不是 `true` 或 `false`。 |
| `missing_file` | 對應檔或技能引用了技能包裡沒有的檔案。 |
| `outside_package` | 對應檔指到技能包資料夾以外的位置。 |
| `linked_file` | 技能包裡有符號連結。 |
| `not_text` | 技能包裡有非文字檔案。 |

沒有任何技能引用到的檔案不構成拒絕理由：技能包也放得下說明文件。

## 掛上去

```python
from agentic_sdk.modules import NextStepWithSkills

plan = NextStepWithSkills(
    api_key=api_key,
    base_url=base_url,
    model="gpt-4o-mini",
    skill_packages=["skill_packages/meeting-notes"],
)
```

技能怎麼被選中、清單的字元預算，見[規劃與推理](plan-modules.md#nextstepwithskills)。
