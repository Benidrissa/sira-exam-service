"use client";
import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getTest, patchTest } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useParams } from "next/navigation";
import { toast } from "sonner";
import { formatError } from "@/lib/formatError";

export default function TestSettingsPage() {
  const params = useParams();
  const testId = params.testId as string;
  const qc = useQueryClient();

  const { data: test, isLoading, error } = useQuery({
    queryKey: ["test", testId],
    queryFn: () => getTest(testId),
  });

  const [weight, setWeight] = useState("");

  useEffect(() => {
    if (test) setWeight(String(test.exam_weight));
  }, [test]);

  // Client-side validation: must be a number between 0 and 100.
  const weightNum = parseFloat(weight);
  const weightInvalid = weight === "" || Number.isNaN(weightNum) || weightNum < 0 || weightNum > 100;

  const save = useMutation({
    mutationFn: () => patchTest(testId, { exam_weight: weightNum }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["test", testId] });
      qc.invalidateQueries({ queryKey: ["submissions", testId] });
      toast.success("Exam weight saved");
    },
    onError: (e) => toast.error(formatError(e)),
  });

  if (isLoading)
    return (
      <main className="max-w-xl mx-auto p-8 space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 w-full rounded-xl" />
      </main>
    );
  if (error) return <p className="p-8 text-destructive">{formatError(error)}</p>;

  return (
    <main className="max-w-xl mx-auto p-8 space-y-6">
      <h1 className="text-2xl font-bold">Test Settings</h1>
      {test && <p className="text-sm text-muted-foreground">{test.title}</p>}

      <Card>
        <CardContent className="space-y-4 py-5">
          <div className="space-y-1.5">
            <label htmlFor="exam_weight" className="text-sm font-medium">
              Weight (% of course grade)
            </label>
            <Input
              id="exam_weight"
              type="number"
              min={0}
              max={100}
              step={0.5}
              value={weight}
              onChange={(e) => setWeight(e.target.value)}
              className="max-w-[12rem]"
              aria-invalid={weightInvalid}
            />
            {weightInvalid && (
              <p className="text-xs text-destructive">Enter a number between 0 and 100.</p>
            )}
            <p className="text-xs text-muted-foreground">
              Relative coefficient of this exam in the course term grade.
            </p>
          </div>

          <Button onClick={() => save.mutate()} disabled={weightInvalid || save.isPending}>
            {save.isPending ? "Saving…" : "Save"}
          </Button>
        </CardContent>
      </Card>
    </main>
  );
}
