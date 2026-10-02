import { Lock, CheckCircle2, List, Loader2 } from 'lucide-react';
import { cn } from '../../lib/utils';
import { useSessionProgress } from '../../api/hooks';

export interface Step {
  name: string;
  label: string;
  icon?: string;
  validated?: boolean;
}

interface StepperNavProps {
  steps: Step[];
  currentStep: number;
  maxUnlocked: number;
  onStepClick: (index: number) => void;
  sessionId?: string;
  pipelineType?: string;
}

export function StepperNav({
  steps,
  currentStep,
  maxUnlocked,
  onStepClick,
  sessionId,
  pipelineType = 'tms',
}: StepperNavProps) {
  // Get real-time progress if sessionId is provided
  const progress = sessionId ? useSessionProgress(sessionId, pipelineType) : null;

  return (
    <div className="border-b bg-background">
      <div className="container mx-auto px-6">
        <div className="flex gap-1 overflow-x-auto justify-center items-center">
          {/* TMS Logo */}
          <div className="flex items-center gap-2 px-4 py-4 mr-2">
            <List className="h-5 w-5 text-primary" />
            <span className="font-semibold text-lg">TMS</span>
          </div>

          {/* Progress indicator (if job is running) */}
          {progress?.isJobRunning && (
            <div className="flex items-center gap-2 px-3 py-2 bg-blue-50 dark:bg-blue-950 rounded-md mr-2">
              <Loader2 className="h-3 w-3 animate-spin text-blue-600" />
              <span className="text-xs text-blue-900 dark:text-blue-100">
                {progress.jobMessage || 'Processing...'}
              </span>
              {progress.jobProgress !== undefined && (
                <span className="text-xs font-medium text-blue-600">
                  {progress.jobProgress}%
                </span>
              )}
            </div>
          )}

          {/* Separator */}
          <div className="h-8 w-px bg-border"></div>

          {steps.map((step, index) => {
          const isLocked = index > maxUnlocked;
          const isCurrent = index === currentStep;
          const isValidated = step.validated;

          return (
            <button
              key={step.name}
              onClick={() => !isLocked && onStepClick(index)}
              disabled={isLocked}
              className={cn(
                'flex items-center gap-2 px-4 py-4 border-b-2 transition-colors whitespace-nowrap text-sm min-w-fit',
                isCurrent
                  ? 'border-primary text-primary font-semibold bg-primary/5'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/50',
                isLocked && 'opacity-50 cursor-not-allowed hover:bg-transparent'
              )}
            >
              {isLocked ? (
                <Lock className="h-4 w-4" />
              ) : isValidated ? (
                <CheckCircle2 className="h-4 w-4 text-green-500" />
              ) : (
                <div className={cn(
                  "h-6 w-6 rounded-full border-2 flex items-center justify-center text-xs",
                  isCurrent ? "border-primary text-primary" : "border-muted-foreground text-muted-foreground"
                )}>
                  {index + 1}
                </div>
              )}
              <span>{step.label}</span>
            </button>
          );
        })}
        </div>
      </div>
    </div>
  );
}
