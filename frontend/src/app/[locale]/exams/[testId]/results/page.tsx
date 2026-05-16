"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { CheckCircle2, XCircle, Clock, FileText, Home } from "lucide-react";

function ResultsContent() {
  const { testId: _testId, locale } = useParams<{ testId: string; locale?: string }>();
  const effectiveLocale = (locale as string) ?? "fr";
  const router = useRouter();
  const searchParams = useSearchParams();

  const attemptId = searchParams.get("attemptId");
  const scoreStr = searchParams.get("score");
  const totalStr = searchParams.get("total");
  const passedStr = searchParams.get("passed");

  const score = scoreStr != null ? parseFloat(scoreStr) : null;
  const total = totalStr != null ? parseFloat(totalStr) : null;
  const passed = passedStr === "true" ? true : passedStr === "false" ? false : null;

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
      <div className="flex items-center gap-3">
        {passed === true ? (
          <CheckCircle2 className="h-8 w-8 text-emerald-500" />
        ) : passed === false ? (
          <XCircle className="h-8 w-8 text-destructive" />
        ) : (
          <Clock className="h-8 w-8 text-muted-foreground" />
        )}
        <div>
          <h1 className="text-2xl font-bold">Exam Submitted</h1>
          <p className="text-sm text-muted-foreground">Your answers have been recorded.</p>
        </div>
        {passed != null && (
          <Badge
            variant={passed ? "success" : "destructive"}
            className="ml-auto text-sm px-3 py-1"
          >
            {passed ? "Passed" : "Not Passed"}
          </Badge>
        )}
      </div>

      {score != null && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">MCQ Score</CardTitle>
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

      <Card>
        <CardHeader className="flex-row items-center gap-3 space-y-0">
          <FileText className="h-5 w-5 text-primary shrink-0" />
          <div>
            <CardTitle className="text-base">Dissertation Answers</CardTitle>
            <CardDescription>
              Your written answers are being graded by AI, followed by your teacher.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <Badge variant="warning">Grading in progress</Badge>
          <p className="mt-3 text-sm text-muted-foreground">
            Your teacher will share final dissertation scores and feedback once grading is complete.
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
