import { PressReleaseStatus } from "@/components/press-releases/status";

export default function Loading() {
  return (
    <main className="release-workbench">
      <section className="release-preview">
        <PressReleaseStatus state="loading" />
      </section>
    </main>
  );
}
