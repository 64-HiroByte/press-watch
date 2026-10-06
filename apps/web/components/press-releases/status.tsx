export type ReleaseDisplayState = "loading" | "error" | "empty" | "no-results";

const messages = {
  loading: { title: "報道発表を読み込んでいます", description: "しばらくお待ちください。" },
  error: { title: "報道発表を取得できませんでした", description: "時間をおいて、もう一度お試しください。" },
  empty: { title: "報道発表はまだありません", description: "報道発表が登録されると、ここに表示されます。" },
  "no-results": { title: "条件に一致する報道発表がありません", description: "キーワードやカテゴリを変えてお試しください。" },
} as const;

export function PressReleaseStatus({ state }: { state: ReleaseDisplayState }) {
  const message = messages[state];

  return (
    <div className="release-status" role={state === "error" ? "alert" : "status"} aria-busy={state === "loading"}>
      <p className="release-status-title">{message.title}</p>
      <p className="release-status-description">{message.description}</p>
      {state === "loading" && (
        <div className="release-skeleton" aria-hidden="true">
          {[0, 1, 2].map((index) => (
            <div className="release-skeleton-row" key={index}>
              <span /><span />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
