# Issue tracker: Local Markdown

Issues 和 specs 存放在本仓库 `.scratch/`。

- 每项功能使用 `.scratch/<feature-slug>/`，spec 为其中的 `spec.md`。
- 每张实施票据单独存为 `issues/<NN>-<slug>.md`，编号从 `01` 开始。
- 文件顶部的 `Status:` 记录 triage 状态，名称见 `docs/agents/triage-labels.md`。
- 评论和对话追加到文件末尾的 `## Comments`。
- “发布到 issue tracker”表示创建对应本地文件；“读取 ticket”表示读取指定文件。仅有编号时，在对应功能目录解析；存在歧义时确认路径。

## Wayfinding operations

- Map 为 `.scratch/<effort>/map.md`，记录 Notes、Decisions-so-far 和 Fog。
- 子票据为 `issues/NN-<slug>.md`，以 `Type:` 记录 research/prototype/grilling/task。
- `Blocked by: NN, NN` 记录依赖；全部依赖为 resolved 后解除阻塞。
- Frontier 按编号选择尚未 resolved、未 claimed 且无阻塞的首张票据。
- 开工前保存 `Status: claimed`。
- 完成后追加 `## Answer`，保存 `Status: resolved`，并在 map 的 Decisions-so-far 追加结论与文件链接。
