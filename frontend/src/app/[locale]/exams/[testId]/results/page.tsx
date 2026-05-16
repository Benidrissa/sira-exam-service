"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { CheckCircle2, Clock, FileText, Home, Info } from "lucide-react";

function ResultsContent() {
  const { testId: _testId, locale } = useParams<{ testId: string; locale?: string }>();
  const effectiveLocale = (locale as string) ?? "fr";
  const router = useRouter();
  const searchParams = useSearchParams();

  const attemptId = searchParams.get("attemptId");
  const scoreStr = searchParams.get("score");
  const totalStr = searchParams.get("total");

  const score = scoreStr != null ? parseFloat(scoreStr) : null;
  const total = totalStr != null ? parseFloat(totalStr) : null;

  if (!attemptId) {
    return (
      <div className="flex justify-center mt-20">
        <Card className="w-full max-w-md text-center">
          <CardHeader>
            <CardTitle>No results found</CardTitle>
            <CardDescription>
              This exam has not been submitted yet, or your session has expired.
            </CardDescription>
          </CardHeader>
          <CardFooter className="justify-center">
            <Button onClick={() => router.push(`/${effectiveLocale}/`)}>
              <Home className="mr-2 h-4 w-4" />
              Return Home
            </Button>
          </CardFooter>
        </Card>
      </div>
    );
  }

  return (
    <main className="max-w-2xl mx-auto p-8 space-y-6">
      {/* Header — neutral, no pass/fail yet */}
      <div className="flex items-center gap-3">
        <CheckCircle2 className="h-8 w-8 text-emerald-500 shrink-0" />
        <div>
          <h1 className="text-2xl font-bold">Exam Submitted</h1>
          <p className="text-sm text-muted-foreground">
            Your answers have been recorded successfully.
          </p>
        </div>
        <Badge variant="warning" className="ml-auto shrink-0">
          Awaiting review
        </Badge>
      </div>

      {/* Notice: final result pending */}
      <Alert>
        <Info className="h-4 w-4" />
        <AlertDescription>
          Your final result will be communicated by your teacher once all grading — including
          the review of written answers — is complete.
        </AlertDescription>
      </Alert>

      {/* MCQ score — automatic, preliminary */}
      {score != null && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Automatic scoring — MCQ</CardTitle>
              <Badge variant="secondary" className="text-xs">Preliminary</Badge>
            </div>
            <CardDescription>
              Multiple-choice questions are scored automatically.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-end gap-2">
              <span className="text-4xl font-bold tabular-nums">{score}</span>
              {total != null && (
                <span className="text-lg text-muted-foreground mb-1">/ {total} questions</span>
              )}
            </div>
            {total != null && total > 0 && (
              <p className="mt-2 text-sm text-muted-foreground">
                {Math.round((score / total) * 100)}% correct
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Dissertation — pending human review */}
      <Card>
        <CardHeader className="flex-row items-center gap-3 space-y-0">
          <FileText className="h-5 w-5 text-primary shrink-0" />
          <div>
            <CardTitle className="text-base">Written answers — Teacher review</CardTitle>
            <CardDescription>
              Your essays are first graded by AI, then reviewed and validated by your teacher.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-amber-500" />
            <Badge variant="warning">Pending teacher review</Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            Your teacher will communicate your written scores and feedback directly.
            This is the authoritative grading step — the final result depends on it.
          </p>
        </CardContent>
      </Card>

      <Separator />

      <div className="flex justify-center">
        <Button variant="outline" onClick={() => router.push(`/${effectiveLocale}/`)}>
          <Home className="mr-2 h-4 w-4" />
          Return Home
        </Button>
      </div>
    </main>
  );
}

export default function ResultsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex justify-center mt-20 text-sm text-muted-foreground">
          Loading results…
        </div>
      }
    >
      <ResultsContent />
    </Suspense>
  );
}
