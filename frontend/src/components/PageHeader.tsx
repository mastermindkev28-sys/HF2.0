export default function PageHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: React.ReactNode }) {
  return (
    <div className="flex items-end justify-between gap-6 border-b border-white/[0.06] px-8 pb-6 pt-8">
      <div>
        <h1 className="font-display text-3xl tracking-tight text-fog-100">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-2xl text-sm text-fog-400">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}
