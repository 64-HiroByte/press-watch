# Railway設定

`railway.ts`は、本人向け限定配置のWeb・APIから取り込んだ設定である。
環境変数は`preserve()`で既存値を保持し、秘密値・通常値ともに保存しない。
新環境では環境変数と手動管理項目を別途用意する必要がある。

SDK・CLIの固定版、認証と接続先の確認、取り込み・照合の手順は[Railway設定のファイル管理](../docs/deployment.md#railway設定のファイル管理)に従う。
実環境へのアクセスは、対象と影響を示して承認を得てから行う。

```bash
pnpm typecheck:railway
pnpm plan:railway
```

planは終了コード0と変更ゼロを確認する。
適用・再配置・CI自動適用は今回の対象外である。
