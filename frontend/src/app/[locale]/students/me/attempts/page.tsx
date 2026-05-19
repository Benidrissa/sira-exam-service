"use client";
import { useQuery } from "@tanstack/react-query";
import { listStudentHistory } from "@/lib/api";
import type { StudentAttemptHistoryItem } from "@/types/exam";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { useParams } from "next/navigation";

export default function MyAttemptsPage() {
  const params = useParams();
  const locale = params.locale as string;

  const { data, isLoading, error } = useQuery({
    queryKey: ["student-history"],
    queryFn: listStudentHistory,
  });

  if (isLoading) return <div className="p-8">Loading…</div>;
  if (error) return <p className="p-8 text-destructive">{String(error)}</p>;

  return (
    <main className="max-w-3xl mx-auto p-8 space-y-6">
      <h1 className="text-2xl font-bold">My Exams</h1>

      {data?.length === 0 && <p className="text-muted-foreground">No completed exams yet.</p>}

      <div className="space-y-3">
        {data?.map((item: StudentAttemptHistoryItem) => (
          <Card key={item.attempt_id}>
            <CardContent className="flex items-center justify-between py-4">
              <div>
                <p className="font-semibold">{item.test_title}</p>
                <p className="text-sm text-muted-foreground">{new Date(item.attempted_at).toLocaleString()}</p>
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
                <Link href={`/${locale}/attempts/${item.attempt_id}/review`}>
                  <Button size="sm" variant="outline">Review</Button>
                </Link>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}
