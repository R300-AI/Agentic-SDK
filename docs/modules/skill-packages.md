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

## 從 GitHub 掛載

技能包的來源有三種：資料夾、zip 壓縮檔、指定版本的公開 git repo。三種都寫在同一個 `skill_packages` 參數裡，Playground 的建構器也是同一套規矩（ADR 0007）。

```python
plan = NextStepWithSkills(
    api_key=api_key,
    base_url=base_url,
    model="gpt-4o-mini",
    skill_packages=[
        "https://github.com/org/meeting-notes.git@v1.2.0",  # repo，版本寫在網址裡
        "skill_packages/local-one",                          # 本機資料夾
        "downloads/another.zip",                             # 壓縮檔
    ],
)
```

只有一個來源時可以不寫成串列。取回的技能包會留在快取裡（預設在使用者的 cache 目錄，或由 `AGENTIC_SDK_SKILL_PACKAGES` 指定），同一個網址加同一個版本只會取回一次，所以跑過一次的流程在沒有網路或 repo 被刪掉時仍然起得來。取回發生在建立規劃模組的時候，不是在執行的時候。

repo 本身就是技能包，沒有再往下一層，所以版面要求是：

```
your-org/meeting-notes/          ← repo 根目錄就是技能包根目錄
├── package.yaml                 ← 必須在根目錄
├── skills/
│   └── minutes/SKILL.md
└── prompts/format.md
```

技能包的名稱取自 repo 名稱（去掉 `.git`，只留英數與 `-_.`）。一個 repo 放一個技能包；把技能包放在 repo 的子目錄底下目前無法掛載。

四項限制，違反時建構器會當場說明：

| 限制 | 內容 |
| --- | --- |
| 只收公開的 repo | 網址不能帶帳號密碼（`https://user:token@…` 會被拒絕），也不支援需要登入的 repo。SDK 另外接受本機的 `file://` repo；Playground 只收 `https`，因為網址是瀏覽器上打進來的。 |
| 版本必須填 | 標籤、分支或 commit 都可以，但一定要指定一個，寫成 `網址@版本`。跟著作者最新的 commit 走，等於 agent 的行為會在沒有人掛載任何東西的情況下改變。 |
| 整個 repo 5 MB 以內 | 取回時不帶歷史（淺層取回後移除 `.git`），計算的是工作目錄的檔案大小。 |
| 每一個檔案都要是文字 | 這條規則對 repo 裡的**所有**檔案生效，不只技能引用到的那些。README 與 LICENSE 沒問題，但 README 裡附的圖片、字型或任何二進位檔會讓整個 repo 被拒絕，錯誤訊息會指出是哪一個檔案。 |

沒有任何技能引用到的檔案不影響掛載：從 repo clone 下來的技能包本來就會帶著 README。

來源被拒絕時丟出的是 `SkillSourceRefused`，帶著 `rule` 與 `source` 兩個欄位——指出是哪一條規矩、哪一個來源。技能包本身不合規則丟 `SkillPackageRefused`，指出的是規則與檔案。兩者分得開：前者是「東西拿不到」，後者是「拿到的東西不合格」。

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
