import { Button } from '../ui/button';
import { ArrowLeft, ArrowRight, CheckCircle } from 'lucide-react';

interface StepperControlsProps {
  currentStep: number;
  totalSteps: number;
  canAdvance: boolean;
  needsValidation: boolean;
  showingComparison?: boolean;
  onBack: () => void;
  onNext: () => void;
  onValidate?: () => void;
  onBackToParams?: () => void;
}

export function StepperControls({
  currentStep,
  totalSteps,
  canAdvance,
  needsValidation,
  showingComparison = false,
  onBack,
  onNext,
  onValidate,
  onBackToParams,
}: StepperControlsProps) {
  return (
    <div className="fixed bottom-6 left-0 right-0 px-6 flex items-center justify-between pointer-events-none z-50">
      <div className="pointer-events-auto">
        {currentStep > 0 && (
          <Button variant="outline" onClick={onBack} size="lg">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Button>
        )}
      </div>

      <div className="pointer-events-auto flex gap-2">
        {/* If showing comparison, show "Back to Parameters" button */}
        {showingComparison && onBackToParams && (
          <Button onClick={onBackToParams} size="lg" variant="outline">
            Back to Parameters
          </Button>
        )}

        {/* If needs validation and NOT showing comparison yet, show "Show Difference" */}
        {needsValidation && !showingComparison && onValidate && (
          <Button onClick={onValidate} size="lg" variant="default">
            <CheckCircle className="h-4 w-4 mr-2" />
            Show Difference
          </Button>
        )}

        {/* If showing comparison, the validation button becomes "Validate & Continue" */}
        {needsValidation && showingComparison && onValidate && (
          <Button onClick={onValidate} size="lg" variant="default">
            <CheckCircle className="h-4 w-4 mr-2" />
            Validate & Continue
          </Button>
        )}

        {/* Next button - disabled when validation needed and not showing comparison */}
        {currentStep < totalSteps - 1 && (
          <Button
            onClick={onNext}
            disabled={!canAdvance}
            size="lg"
            variant={needsValidation && !showingComparison ? 'outline' : 'default'}
            className={needsValidation && !showingComparison ? 'opacity-50' : ''}
          >
            Next
            <ArrowRight className="h-4 w-4 ml-2" />
          </Button>
        )}
      </div>
    </div>
  );
}
