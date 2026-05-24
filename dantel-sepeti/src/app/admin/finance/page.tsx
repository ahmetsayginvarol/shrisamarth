'use client';

import { useState, useEffect, useMemo } from 'react';
import { TrendingUp, TrendingDown, Plus, Trash2, X, Loader2 } from 'lucide-react';
import AdminSidebar from '@/components/admin/AdminSidebar';
import { supabase } from '@/lib/supabase';

type TransactionType = 'income' | 'expense';

interface Transaction {
  id: string;
  type: TransactionType;
  amount: number;
  description: string;
  category: string;
  date: string;
  created_at: string;
}

const CATEGORIES = ['Satış', 'Kargo', 'Reklam', 'Kira', 'Malzeme', 'Diğer'];

const MONTH_NAMES = [
  'Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
  'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık',
];

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('tr-TR', {
    style: 'currency',
    currency: 'TRY',
    minimumFractionDigits: 2,
  }).format(amount);
}

export default function FinancePage() {
  const today = new Date();
  const [selectedMonth, setSelectedMonth] = useState(today.getMonth() + 1);
  const [selectedYear, setSelectedYear] = useState(today.getFullYear());
  const [allTransactions, setAllTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    type: 'income' as TransactionType,
    amount: '',
    description: '',
    category: 'Satış',
    date: today.toISOString().split('T')[0],
  });

  const fetchTransactions = async () => {
    setLoading(true);
    const { data, error } = await supabase
      .from('transactions')
      .select('*')
      .order('date', { ascending: false });
    if (!error && data) setAllTransactions(data);
    setLoading(false);
  };

  useEffect(() => { fetchTransactions(); }, []);

  const transactions = useMemo(
    () => allTransactions.filter(t => {
      const d = new Date(t.date);
      return d.getMonth() + 1 === selectedMonth && d.getFullYear() === selectedYear;
    }),
    [allTransactions, selectedMonth, selectedYear]
  );

  const monthlyIncome = useMemo(
    () => transactions.filter(t => t.type === 'income').reduce((s, t) => s + t.amount, 0),
    [transactions]
  );
  const monthlyExpense = useMemo(
    () => transactions.filter(t => t.type === 'expense').reduce((s, t) => s + t.amount, 0),
    [transactions]
  );
  const netProfit = monthlyIncome - monthlyExpense;
  const allTimeBalance = useMemo(
    () => allTransactions.reduce((s, t) => t.type === 'income' ? s + t.amount : s - t.amount, 0),
    [allTransactions]
  );

  // Last 6 months for bar chart
  const chartData = useMemo(() => {
    return Array.from({ length: 6 }, (_, i) => {
      const d = new Date(selectedYear, selectedMonth - 1 - (5 - i), 1);
      const m = d.getMonth() + 1;
      const y = d.getFullYear();
      const filtered = allTransactions.filter(t => {
        const td = new Date(t.date);
        return td.getMonth() + 1 === m && td.getFullYear() === y;
      });
      return {
        label: MONTH_NAMES[m - 1].slice(0, 3),
        income: filtered.filter(t => t.type === 'income').reduce((s, t) => s + t.amount, 0),
        expense: filtered.filter(t => t.type === 'expense').reduce((s, t) => s + t.amount, 0),
      };
    });
  }, [allTransactions, selectedMonth, selectedYear]);

  const chartMax = Math.max(...chartData.map(d => Math.max(d.income, d.expense)), 1);
  const CHART_H = 120;
  const BAR_W = 18;
  const GROUP_W = 50;
  const SVG_W = chartData.length * GROUP_W;

  // Month/year dropdown options
  const monthOptions = useMemo(() => {
    const opts: { month: number; year: number; label: string }[] = [];
    for (let y = today.getFullYear(); y >= today.getFullYear() - 2; y--) {
      for (let m = 12; m >= 1; m--) {
        if (y === today.getFullYear() && m > today.getMonth() + 1) continue;
        opts.push({ month: m, year: y, label: `${MONTH_NAMES[m - 1]} ${y}` });
      }
    }
    return opts;
  }, []);

  const handleAddTransaction = async () => {
    if (!form.amount || !form.description || !form.date) return;
    setSaving(true);
    const { error } = await supabase.from('transactions').insert({
      type: form.type,
      amount: parseFloat(form.amount),
      description: form.description,
      category: form.category,
      date: form.date,
    });
    if (!error) {
      await fetchTransactions();
      setShowModal(false);
      setForm({ type: 'income', amount: '', description: '', category: 'Satış', date: today.toISOString().split('T')[0] });
    }
    setSaving(false);
  };

  const handleDelete = async (id: string) => {
    await supabase.from('transactions').delete().eq('id', id);
    await fetchTransactions();
    setDeleteConfirm(null);
  };

  return (
    <div className="flex min-h-screen" style={{ backgroundColor: '#0f0809' }}>
      <AdminSidebar />

      <main className="flex-1 p-6 md:p-8 overflow-x-hidden">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl font-bold" style={{ color: '#f8f0ec' }}>Finans</h1>
            <p className="text-sm mt-1" style={{ color: 'rgba(248,240,236,0.45)' }}>Gelir ve gider takibi</p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="btn-gold flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium"
          >
            <Plus size={15} />
            İşlem Ekle
          </button>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <div className="luxury-card p-5 rounded-xl">
            <p className="text-xs font-medium uppercase tracking-widest mb-3" style={{ color: 'rgba(248,240,236,0.45)' }}>Bu Ay Gelir</p>
            <p className="text-xl font-bold" style={{ color: '#4ade80' }}>{formatCurrency(monthlyIncome)}</p>
            <div className="flex items-center gap-1.5 mt-2">
              <TrendingUp size={13} style={{ color: '#4ade80' }} />
              <span className="text-xs" style={{ color: 'rgba(248,240,236,0.45)' }}>
                {MONTH_NAMES[selectedMonth - 1]} {selectedYear}
              </span>
            </div>
          </div>

          <div className="luxury-card p-5 rounded-xl">
            <p className="text-xs font-medium uppercase tracking-widest mb-3" style={{ color: 'rgba(248,240,236,0.45)' }}>Bu Ay Gider</p>
            <p className="text-xl font-bold" style={{ color: '#f87171' }}>{formatCurrency(monthlyExpense)}</p>
            <div className="flex items-center gap-1.5 mt-2">
              <TrendingDown size={13} style={{ color: '#f87171' }} />
              <span className="text-xs" style={{ color: 'rgba(248,240,236,0.45)' }}>
                {MONTH_NAMES[selectedMonth - 1]} {selectedYear}
              </span>
            </div>
          </div>

          <div className="luxury-card p-5 rounded-xl">
            <p className="text-xs font-medium uppercase tracking-widest mb-3" style={{ color: 'rgba(248,240,236,0.45)' }}>Net Kâr</p>
            <p className="text-xl font-bold" style={{ color: netProfit >= 0 ? '#4ade80' : '#f87171' }}>
              {formatCurrency(netProfit)}
            </p>
            <div className="flex items-center gap-1.5 mt-2">
              {netProfit >= 0
                ? <TrendingUp size={13} style={{ color: '#4ade80' }} />
                : <TrendingDown size={13} style={{ color: '#f87171' }} />}
              <span className="text-xs" style={{ color: 'rgba(248,240,236,0.45)' }}>Bu ay</span>
            </div>
          </div>

          <div className="luxury-card p-5 rounded-xl">
            <p className="text-xs font-medium uppercase tracking-widest mb-3" style={{ color: 'rgba(248,240,236,0.45)' }}>Toplam Bakiye</p>
            <p className="text-xl font-bold" style={{ color: allTimeBalance >= 0 ? '#4ade80' : '#f87171' }}>
              {formatCurrency(allTimeBalance)}
            </p>
            <div className="flex items-center gap-1.5 mt-2">
              <span className="text-xs" style={{ color: 'rgba(248,240,236,0.45)' }}>Tüm zamanlar</span>
            </div>
          </div>
        </div>

        {/* Bar Chart */}
        <div className="luxury-card p-6 rounded-xl mb-8">
          <h2 className="text-sm font-semibold mb-6" style={{ color: '#f8f0ec' }}>Son 6 Ay Özeti</h2>
          <div className="overflow-x-auto">
            <svg
              width={SVG_W}
              height={CHART_H + 24}
              style={{ minWidth: '100%' }}
              viewBox={`0 0 ${SVG_W} ${CHART_H + 24}`}
              preserveAspectRatio="xMidYMid meet"
            >
              {chartData.map((d, i) => {
                const x = i * GROUP_W + 6;
                const incomeH = Math.max((d.income / chartMax) * CHART_H, d.income > 0 ? 3 : 0);
                const expenseH = Math.max((d.expense / chartMax) * CHART_H, d.expense > 0 ? 3 : 0);
                return (
                  <g key={i}>
                    <rect
                      x={x}
                      y={CHART_H - incomeH}
                      width={BAR_W}
                      height={incomeH}
                      fill="#4ade80"
                      opacity="0.8"
                      rx="3"
                    >
                      <title>Gelir: {formatCurrency(d.income)}</title>
                    </rect>
                    <rect
                      x={x + BAR_W + 2}
                      y={CHART_H - expenseH}
                      width={BAR_W}
                      height={expenseH}
                      fill="#f87171"
                      opacity="0.8"
                      rx="3"
                    >
                      <title>Gider: {formatCurrency(d.expense)}</title>
                    </rect>
                    <text
                      x={x + BAR_W + 1}
                      y={CHART_H + 16}
                      textAnchor="middle"
                      fontSize="10"
                      fill="rgba(248,240,236,0.45)"
                    >
                      {d.label}
                    </text>
                  </g>
                );
              })}
              <line x1="0" y1={CHART_H} x2={SVG_W} y2={CHART_H} stroke="rgba(212,104,138,0.15)" strokeWidth="1" />
            </svg>
          </div>
          <div className="flex items-center gap-5 mt-4">
            <div className="flex items-center gap-2">
              <span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: '#4ade80' }} />
              <span className="text-xs" style={{ color: 'rgba(248,240,236,0.5)' }}>Gelir</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: '#f87171' }} />
              <span className="text-xs" style={{ color: 'rgba(248,240,236,0.5)' }}>Gider</span>
            </div>
          </div>
        </div>

        {/* Transaction Table */}
        <div className="luxury-card rounded-xl overflow-hidden">
          <div
            className="flex flex-wrap items-center justify-between gap-3 px-5 py-4"
            style={{ borderBottom: '1px solid rgba(212,104,138,0.15)' }}
          >
            <h2 className="text-sm font-semibold" style={{ color: '#f8f0ec' }}>İşlem Geçmişi</h2>
            <select
              value={`${selectedYear}-${selectedMonth}`}
              onChange={e => {
                const [y, m] = e.target.value.split('-');
                setSelectedYear(parseInt(y));
                setSelectedMonth(parseInt(m));
              }}
              className="text-xs rounded-lg px-3 py-1.5 border outline-none"
              style={{
                backgroundColor: '#0f0809',
                color: '#f8f0ec',
                borderColor: 'rgba(212,104,138,0.25)',
              }}
            >
              {monthOptions.map(o => (
                <option key={`${o.year}-${o.month}`} value={`${o.year}-${o.month}`}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 size={30} className="animate-spin" style={{ color: '#d4688a' }} />
            </div>
          ) : transactions.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3">
              <TrendingUp size={36} style={{ color: 'rgba(212,104,138,0.25)' }} />
              <p className="text-sm" style={{ color: 'rgba(248,240,236,0.35)' }}>Bu ay için işlem bulunamadı.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px]">
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(212,104,138,0.12)' }}>
                    {['Tarih', 'Açıklama', 'Kategori', 'Tutar', ''].map(h => (
                      <th
                        key={h}
                        className={`text-xs font-medium uppercase tracking-widest px-5 py-3 ${h === 'Tutar' ? 'text-right' : 'text-left'}`}
                        style={{ color: 'rgba(248,240,236,0.4)' }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((t, idx) => (
                    <tr
                      key={t.id}
                      style={{
                        borderBottom: idx < transactions.length - 1 ? '1px solid rgba(212,104,138,0.07)' : 'none',
                      }}
                    >
                      <td className="px-5 py-3 text-sm" style={{ color: 'rgba(248,240,236,0.55)', whiteSpace: 'nowrap' }}>
                        {new Date(t.date).toLocaleDateString('tr-TR')}
                      </td>
                      <td className="px-5 py-3 text-sm" style={{ color: '#f8f0ec' }}>{t.description}</td>
                      <td className="px-5 py-3">
                        <span
                          className="text-xs px-2 py-0.5 rounded-full"
                          style={{
                            backgroundColor: 'rgba(212,104,138,0.1)',
                            color: '#d4688a',
                            border: '1px solid rgba(212,104,138,0.2)',
                          }}
                        >
                          {t.category}
                        </span>
                      </td>
                      <td
                        className="px-5 py-3 text-sm font-semibold text-right"
                        style={{ color: t.type === 'income' ? '#4ade80' : '#f87171', whiteSpace: 'nowrap' }}
                      >
                        {t.type === 'income' ? '+' : '−'}{formatCurrency(t.amount)}
                      </td>
                      <td className="px-4 py-3">
                        {deleteConfirm === t.id ? (
                          <div className="flex items-center gap-1.5 justify-end">
                            <button
                              onClick={() => handleDelete(t.id)}
                              className="text-xs px-2 py-0.5 rounded font-medium"
                              style={{ backgroundColor: '#f87171', color: '#0f0809' }}
                            >
                              Sil
                            </button>
                            <button
                              onClick={() => setDeleteConfirm(null)}
                              className="text-xs px-2 py-0.5 rounded font-medium"
                              style={{ backgroundColor: 'rgba(248,240,236,0.1)', color: '#f8f0ec' }}
                            >
                              İptal
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setDeleteConfirm(t.id)}
                            className="block ml-auto opacity-30 hover:opacity-80 transition-opacity"
                            style={{ color: '#f87171' }}
                            title="Sil"
                          >
                            <Trash2 size={14} />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>

      {/* Add Transaction Modal */}
      {showModal && (
        <div
          className="modal-backdrop fixed inset-0 z-50 flex items-center justify-center p-4"
          onClick={e => { if (e.target === e.currentTarget) setShowModal(false); }}
        >
          <div
            className="luxury-card rounded-2xl w-full max-w-md p-6 shadow-2xl"
            style={{ backgroundColor: '#180d10' }}
          >
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-base font-semibold" style={{ color: '#f8f0ec' }}>İşlem Ekle</h3>
              <button
                onClick={() => setShowModal(false)}
                className="opacity-50 hover:opacity-100 transition-opacity"
                style={{ color: '#f8f0ec' }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Type Toggle */}
            <div
              className="flex rounded-lg overflow-hidden mb-5"
              style={{ border: '1px solid rgba(212,104,138,0.2)' }}
            >
              <button
                onClick={() => setForm(f => ({ ...f, type: 'income' }))}
                className="flex-1 py-2 text-sm font-medium transition-colors"
                style={{
                  backgroundColor: form.type === 'income' ? '#4ade80' : 'transparent',
                  color: form.type === 'income' ? '#0f0809' : 'rgba(248,240,236,0.5)',
                }}
              >
                Gelir
              </button>
              <button
                onClick={() => setForm(f => ({ ...f, type: 'expense' }))}
                className="flex-1 py-2 text-sm font-medium transition-colors"
                style={{
                  backgroundColor: form.type === 'expense' ? '#f87171' : 'transparent',
                  color: form.type === 'expense' ? '#0f0809' : 'rgba(248,240,236,0.5)',
                }}
              >
                Gider
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium mb-1.5" style={{ color: 'rgba(248,240,236,0.55)' }}>
                  Tutar (₺)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={form.amount}
                  onChange={e => setForm(f => ({ ...f, amount: e.target.value }))}
                  placeholder="0,00"
                  className="w-full px-3 py-2 rounded-lg text-sm border outline-none focus:ring-1"
                  style={{
                    backgroundColor: '#0f0809',
                    color: '#f8f0ec',
                    borderColor: 'rgba(212,104,138,0.2)',
                    '--tw-ring-color': '#d4688a',
                  } as React.CSSProperties}
                />
              </div>

              <div>
                <label className="block text-xs font-medium mb-1.5" style={{ color: 'rgba(248,240,236,0.55)' }}>
                  Açıklama
                </label>
                <input
                  type="text"
                  value={form.description}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                  placeholder="İşlem açıklaması"
                  className="w-full px-3 py-2 rounded-lg text-sm border outline-none focus:ring-1"
                  style={{
                    backgroundColor: '#0f0809',
                    color: '#f8f0ec',
                    borderColor: 'rgba(212,104,138,0.2)',
                    '--tw-ring-color': '#d4688a',
                  } as React.CSSProperties}
                />
              </div>

              <div>
                <label className="block text-xs font-medium mb-1.5" style={{ color: 'rgba(248,240,236,0.55)' }}>
                  Kategori
                </label>
                <select
                  value={form.category}
                  onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg text-sm border outline-none"
                  style={{
                    backgroundColor: '#0f0809',
                    color: '#f8f0ec',
                    borderColor: 'rgba(212,104,138,0.2)',
                  }}
                >
                  {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium mb-1.5" style={{ color: 'rgba(248,240,236,0.55)' }}>
                  Tarih
                </label>
                <input
                  type="date"
                  value={form.date}
                  onChange={e => setForm(f => ({ ...f, date: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg text-sm border outline-none"
                  style={{
                    backgroundColor: '#0f0809',
                    color: '#f8f0ec',
                    borderColor: 'rgba(212,104,138,0.2)',
                    colorScheme: 'dark',
                  }}
                />
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setShowModal(false)}
                className="btn-ghost flex-1 py-2 rounded-lg text-sm font-medium"
              >
                İptal
              </button>
              <button
                onClick={handleAddTransaction}
                disabled={saving || !form.amount || !form.description}
                className="btn-gold flex-1 py-2 rounded-lg text-sm font-medium disabled:opacity-40 flex items-center justify-center gap-2"
              >
                {saving && <Loader2 size={14} className="animate-spin" />}
                {saving ? 'Kaydediliyor...' : 'Kaydet'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
