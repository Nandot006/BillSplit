export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex flex-1 flex-col items-center justify-center px-4 py-16">
      <div className="w-full max-w-sm">
        <p className="mb-8 font-[family-name:var(--font-display)] text-2xl font-bold">BillSplit</p>
        {children}
      </div>
    </main>
  );
}
