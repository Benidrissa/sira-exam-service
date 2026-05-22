"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listStudentHistory } from "@/lib/api";
import type { StudentAttemptHistoryItem } from "@/types/exam";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ChevronDown, ChevronRight, Archive } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { formatError } from "@/lib/formatError";
import { Select } from "@/components/ui/select";
import { useDebounce } from "@/hooks/use-debounce";

// ─── Grouping ─────────────────────────────────────────────────────────────────
type ClassGroup = {
  class_name: string | null;
  academic_year: string | null;
  class_archived_at: string | null;
  attempts: StudentAttemptHistoryItem[];
};
type CourseGroup = {
  course_key: string;
  course_code: string | null;
  course_name: string | null;
  classes: ClassGroup[];
};

function buildCourseGroups(items: StudentAttemptHistoryItem[]): CourseGroup[] {
  const courseMap = new Map<string, Map<string, ClassGroup>>();
  const courseMeta = new Map<string, { course_code: string | null; course_name: string | null }>();

  for (const item of items) {
    const courseKey = item.course_code ?? item.course_name ?? "__other__";
    const classKey = item.class_name ?? `__none_${item.academic_year ?? ""}`;

    if (!courseMap.has(courseKey)) {
      courseMap.set(courseKey, new Map());
      courseMeta.set(courseKey, { course_code: item.course_code, course_name: item.course_name });
    }
    const classMap = courseMap.get(courseKey)!;
    if (!classMap.has(classKey)) {
      classMap.set(classKey, { class_name: item.class_name, academic_year: item.academic_year, class_archived_at: item.class_archived_at, attempts: [] });
    }
    classMap.get(classKey)!.attempts.push(item);
  }

  return [...courseMap.entries()].map(([courseKey, classMap]) => {
    const meta = courseMeta.get(courseKey)!;
    const classes = [...classMap.values()].sort((a, b) => {
      if (a.class_archived_at && !b.class_archived_at) return 1;
      if (!a.class_archived_at && b.class_archived_at) return -1;
      return (a.class_name ?? "").localeCompare(b.class_name ?? "");
    });
    return { course_key: courseKey, course_code: meta.course_code, course_name: meta.course_name, classes };
  });
}

// ─── Class sub-accordion ──────────────────────────────────────────────────────
function ClassAccordion({ group, locale }: { group: ClassGroup; locale: string }) {
  const isArchived = !!group.class_archived_at;
  const [open, setOpen] = useState(!isArchived);
  const label = group.class_name
    ? `${group.class_name}${group.academic_year ? ` (${group.academic_year})` : ""}`
    : "No class";

  return (
    <div className={`border rounded-lg ${isArchived ? "opacity-60" : ""}`}>
      <button
        onClick={() => setOpen(v => !v)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-sm font-medium hover:bg-muted/50 transition-colors"
      >
        <span className="flex items-center gap-2">
          {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          {label}
          {isArchived && (
            <span className="flex items-center gap-1 text-xs font-normal text-muted-foreground">
              <Archive className="h-3 w-3" /> Archived
            </span>
          )}
          <Badge variant="outline" className="text-xs py-0">{group.attempts.length}</Badge>
        </span>
      </button>

      {open && (
        <div className="border-t space-y-2 p-3">
          {group.attempts.map((item) => (
            <Card key={item.attempt_id}>
              <CardContent className="flex items-center justify-between py-3">
                <div>
                  <p className="font-medium text-sm">{item.test_title}</p>
                  <p className="text-xs text-muted-foreground">{new Date(item.attempted_at).toLocaleString()}</p>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-sm text-right">
                    <p className="font-medium">{item.total_score?.toFixed(1) ?? "—"} pts</p>
                    {item.passed != null && (
                      <Badge className={item.passed ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}>
                        {item.passed ? "Passed" : "Failed"}
                      </Badge>
                    )}
                  </div>
                  {item.review_allowed && (
                    <Link href={`/${locale}/attempts/${item.attempt_id}/review`}>
                      <Button size="sm" variant="outline">Review</Button>
                    </Link>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function MyAttemptsPage() {
  const params = useParams();
  const locale = params.locale as string;
  const [search, setSearch] = useState("");
  const [passedFilter, setPassedFilter] = useState("");
  const debouncedSearch = useDebounce(search, 300);

  const { data, isLoading, error } = useQuery({
    queryKey: ["student-history"],
    queryFn: listStudentHistory,
    staleTime: 30_000,
  });

  if (isLoading) return (
    <main className="max-w-3xl mx-auto p-8 space-y-6">
      <Skeleton className="h-8 w-48" />
      {[1, 2, 3].map(i => <Skeleton key={i} className="h-24 w-full rounded-xl" />)}
    </main>
  );
  if (error) return <p className="p-8 text-destructive">{formatError(error)}</p>;

  const allItems = data ?? [];

  // Apply filters to flat list before grouping
  const filtered = allItems.filter((item) => {
    const matchSearch = !debouncedSearch || item.test_title.toLowerCase().includes(debouncedSearch.toLowerCase());
    const matchPassed = !passedFilter
      || (passedFilter === "passed" ? item.passed === true : item.passed === false);
    return matchSearch && matchPassed;
  });

  const courseGroups = buildCourseGroups(filtered);

  return (
    <main className="max-w-3xl mx-auto p-8 space-y-6">
      <h1 className="text-2xl font-bold">My Exams</h1>

      {allItems.length > 0 && (
        <div className="flex flex-col sm:flex-row gap-3">
          <Input
            placeholder="Search by exam title…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="max-w-xs"
          />
          <Select
            options={[{ value: "passed", label: "Passed" }, { value: "failed", label: "Failed" }]}
            placeholder="All results"
            value={passedFilter}
            onChange={e => setPassedFilter(e.target.value)}
            className="w-36"
          />
          {(debouncedSearch || passedFilter) && (
            <span className="self-center text-sm text-muted-foreground">{filtered.length} result{filtered.length !== 1 ? "s" : ""}</span>
          )}
        </div>
      )}

      {allItems.length === 0 && (
        <div className="py-12 text-center text-muted-foreground space-y-2">
          <p className="font-medium">No completed exams yet.</p>
          <p className="text-sm">Your results will appear here once you submit an exam and your instructor validates it.</p>
        </div>
      )}

      {allItems.length > 0 && courseGroups.length === 0 && (
        <p className="text-sm text-muted-foreground">No exams match your filters.</p>
      )}

      {courseGroups.map((course) => (
        <section key={course.course_key}>
          <div className="mb-2">
            <h2 className="text-lg font-semibold">
              {course.course_code
                ? `${course.course_code}${course.course_name ? ` — ${course.course_name}` : ""}`
                : (course.course_name ?? "Other")}
            </h2>
          </div>
          <div className="space-y-2">
            {course.classes.map((cls, i) => (
              <ClassAccordion key={`${course.course_key}_${cls.class_name ?? i}`} group={cls} locale={locale} />
            ))}
          </div>
        </section>
      ))}
    </main>
  );
}
