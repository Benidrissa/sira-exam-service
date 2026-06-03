"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getCourseSummary } from "@/lib/api";
import type { CourseSummaryGroup } from "@/types/exam";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ChevronDown, ChevronRight, Archive } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { formatError } from "@/lib/formatError";

// Group the flat course-summary list by academic_year (descending).
function byYearDesc(groups: CourseSummaryGroup[]): [string, CourseSummaryGroup[]][] {
  const map = new Map<string, CourseSummaryGroup[]>();
  for (const g of groups) {
    if (!map.has(g.academic_year)) map.set(g.academic_year, []);
    map.get(g.academic_year)!.push(g);
  }
  return [...map.entries()].sort((a, b) => b[0].localeCompare(a[0]));
}

function CourseCard({ group, locale }: { group: CourseSummaryGroup; locale: string }) {
  const isArchived = !!group.class_archived_at;
  const [open, setOpen] = useState(!isArchived);

  return (
    <Card className={isArchived ? "opacity-70" : ""}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-muted/50 transition-colors"
      >
        <span className="flex items-center gap-2">
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          <span>
            <span className="font-semibold">
              {group.course_code}
              {group.course_name ? ` — ${group.course_name}` : ""}
            </span>
            <span className="ml-2 text-sm text-muted-foreground">{group.class_name}</span>
          </span>
          <Badge variant="outline" className="text-xs uppercase">{group.quarter}</Badge>
          {isArchived && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <Archive className="h-3 w-3" /> Archived
            </span>
          )}
        </span>
        <span className="flex items-center gap-2 text-sm">
          {group.weighted_avg != null && (
            <span className="font-medium">{group.weighted_avg.toFixed(1)}</span>
          )}
          {group.grade_letter && (
            <Badge className="bg-blue-100 text-blue-700">{group.grade_letter}</Badge>
          )}
        </span>
      </button>

      {open && (
        <CardContent className="border-t pt-3">
          <table className="w-full text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr className="text-left">
                <th className="pb-2 font-medium">Title</th>
                <th className="pb-2 font-medium text-right">Weight</th>
                <th className="pb-2 font-medium text-right">Score</th>
                <th className="pb-2 font-medium text-right">Result</th>
              </tr>
            </thead>
            <tbody>
              {group.exams.map((exam) => {
                const reviewable = exam.feedback_available && exam.attempt_id != null;
                const titleCell = reviewable ? (
                  <Link
                    href={`/${locale}/attempts/${exam.attempt_id}/review`}
                    className="text-blue-600 hover:underline"
                  >
                    {exam.test_title}
                  </Link>
                ) : (
                  exam.test_title
                );
                return (
                  <tr key={exam.test_id} className="border-t">
                    <td className="py-2">{titleCell}</td>
                    <td className="py-2 text-right text-muted-foreground">
                      {exam.exam_weight}%
                    </td>
                    <td className="py-2 text-right">
                      {exam.dispensed ? (
                        <Badge variant="outline">Exempt</Badge>
                      ) : exam.score != null ? (
                        exam.score.toFixed(1)
                      ) : exam.attempt_id == null ? (
                        <span className="text-muted-foreground" title="Not attempted">—</span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-2 text-right">
                      {exam.dispensed ? (
                        <span className="text-muted-foreground">—</span>
                      ) : exam.passed != null ? (
                        <Badge
                          className={
                            exam.passed
                              ? "bg-green-100 text-green-700"
                              : "bg-red-100 text-red-700"
                          }
                        >
                          {exam.passed ? "Passed" : "Failed"}
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="mt-3 flex items-center justify-end gap-2 border-t pt-3 text-sm">
            <span className="text-muted-foreground">Weighted average:</span>
            <span className="font-semibold">
              {group.weighted_avg != null ? group.weighted_avg.toFixed(1) : "—"}
            </span>
            {group.grade_letter && (
              <Badge className="bg-blue-100 text-blue-700">{group.grade_letter}</Badge>
            )}
          </div>
        </CardContent>
      )}
    </Card>
  );
}

export default function MyCoursesPage() {
  const params = useParams();
  const locale = params.locale as string;

  const { data, isLoading, error } = useQuery({
    queryKey: ["course-summary"],
    queryFn: getCourseSummary,
    staleTime: 30_000,
  });

  if (isLoading)
    return (
      <main className="max-w-3xl mx-auto p-8 space-y-6">
        <Skeleton className="h-8 w-48" />
        {[1, 2].map((i) => (
          <Skeleton key={i} className="h-32 w-full rounded-xl" />
        ))}
      </main>
    );
  if (error) return <p className="p-8 text-destructive">{formatError(error)}</p>;

  const groups = data ?? [];
  const years = byYearDesc(groups);

  return (
    <main className="max-w-3xl mx-auto p-8 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">My Courses</h1>
        <Link href={`/${locale}/students/me/attempts`} className="text-sm text-blue-600 hover:underline">
          My Exams
        </Link>
      </div>

      {groups.length === 0 && (
        <div className="py-12 text-center text-muted-foreground space-y-2">
          <p className="font-medium">No course history yet</p>
          <p className="text-sm">Your term grades will appear here once exams are scheduled in your classes.</p>
        </div>
      )}

      {years.map(([year, yearGroups]) => (
        <section key={year} className="space-y-3">
          <h2 className="text-lg font-semibold text-muted-foreground">{year}</h2>
          {yearGroups.map((g) => (
            <CourseCard key={`${g.course_code}_${g.class_id}_${g.quarter}`} group={g} locale={locale} />
          ))}
        </section>
      ))}
    </main>
  );
}
