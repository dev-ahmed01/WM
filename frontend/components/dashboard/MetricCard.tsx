import React from 'react';
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';

interface MetricCardProps {
  title: string;
  value: string | number;
  change?: string;
  trend?: 'up' | 'down' | 'neutral';
}

export function MetricCard({ title, value, change, trend = 'neutral' }: MetricCardProps) {
  const TrendIcon = trend === 'up' ? ArrowUpRight : trend === 'down' ? ArrowDownRight : Minus;
  return (
    <div className="wm-panel flex min-h-32 flex-col justify-between p-5">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-semibold text-muted-foreground">{title}</span>
        {change ? <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-[10px] font-semibold ${trend === 'up' ? 'bg-emerald-50 text-emerald-700' : trend === 'down' ? 'bg-red-50 text-red-700' : 'bg-muted text-muted-foreground'}`}><TrendIcon className="h-3 w-3" />{change}</span> : null}
      </div>
      <span className="mt-5 text-2xl font-semibold tracking-[-0.035em] text-foreground">{value}</span>
    </div>
  );
}
