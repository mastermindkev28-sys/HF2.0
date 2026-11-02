"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Clapperboard, Boxes, Film, Users, FolderOpen, Settings } from "lucide-react";
import BackendPill from "./BackendPill";

const NAV = [
  { href: "/", label: "Create", icon: Clapperboard },
  { href: "/models/", label: "Explore Models", icon: Boxes },
  { href: "/generations/", label: "My Generations", icon: Film },
  { href: "/characters/", label: "Characters", icon: Users },
  { href: "/assets/", label: "Assets", icon: FolderOpen },
  { href: "/settings/", label: "Settings", icon: Settings },
];

export default function Sidebar() {
  const path = usePathname();
  return (
    <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col border-r border-white/[0.06] bg-ink-950 px-3 py-5">
      <Link href="/" className="mb-8 flex items-center gap-2.5 px-3">
        <div className="grid h-7 w-7 place-items-center rounded-lg bg-accent text-[13px] font-black text-ink-950">H</div>
        <div className="leading-tight">
          <div className="text-sm font-semibold tracking-tight">HIGGS Studio</div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-fog-500">Private · Local</div>
        </div>
      </Link>
      <nav className="flex flex-col gap-0.5">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? path === "/" : path.startsWith(href.replace(/\/$/, ""));
          return (
            <Link key={href} href={href}
              className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition ${active ? "bg-white/[0.06] text-fog-100" : "text-fog-400 hover:bg-white/[0.03] hover:text-fog-100"}`}>
              <Icon size={16} strokeWidth={1.75} className={active ? "text-accent" : ""} />
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto"><BackendPill /></div>
    </aside>
  );
}
