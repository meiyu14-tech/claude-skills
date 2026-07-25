# claude-skills

幸せ貢献業のAI共通スキル リポジトリ（共有書棚）。
Claude CodeとCowork（デスクトップアプリ）が**同じスキルで動く**ためのプラグインマーケットプレイス。

## 目的

- スキルの正本を1か所（このリポジトリ）に置き、全AI・全PCが同じスキルを使う
- Vault本体（機密情報を含む）とは分離し、スキル定義のみを保存する

## 構成（プラグインマーケットプレイス形式）

```
claude-skills/
├─ .claude-plugin/
│   └─ marketplace.json          マーケットプレイス定義（名前：shiawase）
└─ plugins/
    └─ shiawase-skills/          プラグイン本体
        ├─ .claude-plugin/
        │   └─ plugin.json
        └─ skills/
            ├─ common-rules/     全スキル共通の運用ルール（正本・14項）
            ├─ asa/              朝の全体把握。期限切れ・放置・予定を集めて今日やる3つを出す
            ├─ douga/            動画URLを内容のわかるタスク（Trelloカード＋台帳）に変換する
            ├─ gijiroku/        会議記録を8項目のMarkdown議事録にまとめる
            ├─ kikaku/           社内判断用の企画書（Markdown）を生成する
            ├─ sop/              業務フローから13列のSOP Excelを生成する
            ├─ zukai/            初めて触る人向けのHTML取扱説明フローを生成する
            └─ zukai-edit/       zukaiで作成したHTMLを修正する
```

## 使い方

### Claude Code（初回のみ）

```
/plugin marketplace add meiyu14-tech/claude-skills
/plugin install shiawase-skills@shiawase
```

呼び出し例：`/shiawase-skills:sop`

### Cowork（デスクトップアプリ・初回のみ）

1. ワークスペースの「カスタマイズ」を開く
2. 「プラグイン」タブ → 「マーケットプレイスを追加」
3. `https://github.com/meiyu14-tech/claude-skills.git` を貼り付ける
4. `shiawase-skills` の「インストール」を押す

## 運用ルール

- スキルの正本はこのリポジトリ。追加・修正したら必ずコミット・プッシュする
- 機密情報（顧客名・金額・契約内容・原発関連の固有名詞）はスキルに書かない
- スキルの追加は `plugins/shiawase-skills/skills/<スキル名>/SKILL.md` を作成する
- 更新後、各環境では `/plugin update` またはマーケットプレイスの再読み込みで最新化される
