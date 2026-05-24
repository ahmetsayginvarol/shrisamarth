'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  Package,
  ShoppingBag,
  Users,
  TrendingUp,
  Settings,
  LogOut,
} from 'lucide-react';

const navItems = [
  { href: '/admin', label: 'Panel', icon: LayoutDashboard, exact: true },
  { href: '/admin/products', label: 'Ürünler', icon: Package },
  { href: '/admin/orders', label: 'Siparişler', icon: ShoppingBag },
  { href: '/admin/customers', label: 'Müşteriler', icon: Users },
  { href: '/admin/finance', label: 'Finans', icon: TrendingUp },
  { href: '/admin/settings', label: 'Ayarlar', icon: Settings },
];

export default function AdminSidebar() {
  const pathname = usePathname();

  const isActive = (href: string, exact?: boolean) =>
    exact ? pathname === href : pathname.startsWith(href);

  return (
    <aside
      className="hidden md:flex flex-col w-56 min-h-screen py-6 px-3 shrink-0"
      style={{
        backgroundColor: '#180d10',
        borderRight: '1px solid rgba(212,104,138,0.12)',
      }}
    >
      {/* Logo */}
      <div className="px-3 mb-8">
        <span
          className="text-lg font-bold tracking-wide"
          style={{ color: '#d4688a' }}
        >
          Dantel Sepeti
        </span>
        <p className="text-xs mt-0.5" style={{ color: 'rgba(248,240,236,0.35)' }}>Yönetim Paneli</p>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-0.5">
        {navItems.map(({ href, label, icon: Icon, exact }) => {
          const active = isActive(href, exact);
          return (
            <Link
              key={href}
              href={href}
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors"
              style={{
                backgroundColor: active ? 'rgba(212,104,138,0.15)' : 'transparent',
                color: active ? '#d4688a' : 'rgba(248,240,236,0.55)',
              }}
            >
              <Icon size={16} />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="pt-4" style={{ borderTop: '1px solid rgba(212,104,138,0.12)' }}>
        <button
          className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium w-full transition-colors hover:bg-white/5"
          style={{ color: 'rgba(248,240,236,0.4)' }}
        >
          <LogOut size={16} />
          Çıkış Yap
        </button>
      </div>
    </aside>
  );
}
