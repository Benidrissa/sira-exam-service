import * as React from "react";
import { cn } from "@/lib/utils";

interface SeparatorProps extends React.HTMLAttributes<HTMLHRElement> {
  orientation?: "horizontal" | "vertical";
}

const Separator = React.forwardRef<HTMLHRElement, SeparatorProps>(
  ({ className, orientation = "horizontal", ...props }, ref) => (
    <hr
      ref={ref}
      className={cn(
        "shrink-0 border-border",
        orientation === "horizontal" ? "h-px w-full border-t" : "h-full w-px border-l",
        className
      )}
      {...props}
    />
  )
);
Separator.displayName = "Separator";

export { Separator };
