import { cn } from "@/lib/utils";

interface LoadingSpinnerProps {
  className?: string;
  size?: "sm" | "default" | "lg";
}

export function LoadingSpinner({ className, size = "default" }: LoadingSpinnerProps) {
  const sizeClass = size === "sm" ? "h-3 w-3" : size === "lg" ? "h-6 w-6" : "h-4 w-4";
  return (
    <span
      className={cn(
        "inline-block animate-spin rounded-full border-2 border-current border-t-transparent",
        sizeClass,
        className
      )}
      aria-label="Loading"
    />
  );
}
