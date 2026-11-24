import { SystemStatus } from "@/components/common/SystemStatus";

// PHASE 1 placeholder. The full dashboard is built in PHASE 2.
export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-8 p-8">
      <div className="text-center">
        <h1 className="text-2xl font-bold">Personal AI Work Assistant</h1>
        <p className="mt-2 text-sm text-black/60 dark:text-white/60">Local AI Meeting Agent · PHASE 1</p>
      </div>
      <SystemStatus />
    </main>
  );
}
