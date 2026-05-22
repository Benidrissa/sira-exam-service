import { cn } from "@/lib/utils";

interface SelectOption {
  label: string;
  value: string;
}

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  options: SelectOption[];
  placeholder?: string;
}

export function Select({ options, placeholder, className, ...props }: SelectProps) {
  return (
    <select
      className={cn(
        "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm",
        "shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1",
        "focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    >
      {placeholder && (
        <option value="">{placeholder}</option>
      )}
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}
