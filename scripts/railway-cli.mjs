import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const binary = fileURLToPath(new URL("../tmp/tools/railway/5.71.0/railway", import.meta.url));
const args = process.argv.slice(2);
const allowed =
  (args.length === 1 && args[0] === "--version") ||
  ["login", "link"].includes(args[0]) ||
  (args[0] === "config" && ["pull", "plan"].includes(args[1]));
const forbidden = [
  "--include-variables",
  "--decrypt-variables",
  "--show-values",
  "--omit-preserved-variables",
  "--runner",
  "--json",
  "--out",
];

if (
  !allowed ||
  args.some((arg) => forbidden.some((flag) => arg === flag || arg.startsWith(`${flag}=`)))
) {
  console.error("この入口は版確認・認証・接続先選択・秘密値を展開しないpull/plan専用です。");
  process.exit(1);
}
if (
  args[0] === "config" &&
  args[1] === "pull" &&
  (!args.includes("--variables=managed") ||
    args.some((arg) => arg.startsWith("--variables") && arg !== "--variables=managed"))
) {
  console.error("pullには--variables=managedを明示してください。");
  process.exit(1);
}
if (!existsSync(binary)) {
  console.error("固定CLIがありません。docs/deployment.mdの導入手順を確認してください。");
  process.exit(1);
}
if (
  args[0] === "config" &&
  args[1] === "plan" &&
  !existsSync(new URL("../.railway/railway.ts", import.meta.url))
) {
  console.error("設定は未取り込みです。実環境の読み取り承認後にpullを行ってください。");
  process.exit(1);
}

// SDKのnative評価は環境変数_を使ってCLIの版を確認する。
const env = { ...process.env, RAILWAY_NO_AUTO_UPDATE: "1", _: binary };
// 旧runnerへの切替を継承せず、固定CLIのnative engineを使う。
delete env.RAILWAY_IAC_TS_BIN;
delete env.RAILWAY_IAC_ENGINE;
const version = spawnSync(binary, ["--version"], { cwd: root, env, encoding: "utf8" });
if (version.status !== 0 || version.stdout.trim() !== "railway 5.71.0") {
  console.error("CLIの版を確認できません。5.71.0以外は実行しません。");
  process.exit(1);
}
const result = spawnSync(binary, args, { cwd: root, env, stdio: "inherit" });
if (result.error) console.error("Railway CLIを起動できませんでした。");
process.exit(result.status ?? 1);
