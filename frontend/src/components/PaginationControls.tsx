"use client";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface PaginationControlsProps {
  currentPage: number;
  totalPages: number;
  totalItems: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}

export function PaginationControls({
  currentPage, totalPages, totalItems, pageSize, onPageChange,
}: PaginationControlsProps) {
  if (totalItems === 0) return null;

  const showFrom = totalItems === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const showTo = Math.min(currentPage * pageSize, totalItems);

  return (
    <div className="flex items-center justify-between pt-3 text-sm text-muted-foreground">
      <span>Showing {showFrom}–{showTo} of {totalItems}</span>
      <div className="flex items-center gap-2">
        <Button
          variant="outline" size="sm"
          disabled={currentPage <= 1}
          onClick={() => onPageChange(currentPage - 1)}
          aria-label="Previous page"
        >
          <ChevronLeft className="h-4 w-4" />
          Prev
        </Button>
        <span className="text-xs font-medium">Page {currentPage} / {totalPages}</span>
        <Button
          variant="outline" size="sm"
          disabled={currentPage >= totalPages}
          onClick={() => onPageChange(currentPage + 1)}
          aria-label="Next page"
        >
          Next
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
