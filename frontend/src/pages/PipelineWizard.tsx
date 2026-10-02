import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useSessionStages, useIsAutomatedSession } from '../api/hooks';
import { StepperNav } from '../components/wizard/StepperNav';
import { StepperControls } from '../components/wizard/StepperControls';
import { Card, CardContent } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Loader2, Eye, AlertCircle, Edit } from 'lucide-react';

interface Step {
  name: string;
  label: string;
  validated?: boolean;
}

// Import step components
import { LoadingStep } from './steps/tms/LoadingStep';
import { MetadataStep } from './steps/tms/MetadataStep';
import { InitialQCStep } from './steps/tms/InitialQCStep';
import { CorrectionStep } from './steps/tms/CorrectionStep';
import { CalibrationStep } from './steps/tms/CalibrationStep';
import { FinalQCStep } from './steps/tms/FinalQCStep';
import { ProductionStep } from './steps/tms/ProductionStep';

export function PipelineWizard() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(0);
  const [maxUnlocked, setMaxUnlocked] = useState(0);
  const [validatedSteps, setValidatedSteps] = useState<Set<number>>(new Set());
  // Track which QC steps are showing comparison view
  const [qcStepsShowingComparison, setQcStepsShowingComparison] = useState<Record<number, boolean>>({});

  // For MVP, hardcode TMS pipeline type
  // In production, this would come from job metadata
  const pipelineType = 'tms';

  // Detect if this is an automated session
  const { isAutomated, status: automatedStatus } = useIsAutomatedSession(sessionId || null, pipelineType);

  const { data: stagesData, isLoading, error } = useSessionStages(
    sessionId || null,
    pipelineType
  );

  // All 7 TMS pipeline steps (defined early to avoid hook dependency issues)
  const steps: Step[] = [
    { name: 'merged', label: 'Loading & Continuity' },
    { name: 'with_metadata', label: 'Metadata' },
    { name: 'initial_qc', label: 'Initial QC' },
    { name: 'corrected', label: 'Signal Correction' },
    { name: 'calibrated', label: 'VWC Calibration' },
    { name: 'final', label: 'Final QC' },
    { name: 'production', label: 'Production' },
  ];

  // Save current step to localStorage whenever it changes
  // IMPORTANT: This useEffect must be BEFORE any early returns to maintain hook order
  useEffect(() => {
    if (sessionId && steps[currentStep]) {
      localStorage.setItem(`current_step_${sessionId}`, steps[currentStep].label);
    }
  }, [currentStep, sessionId]);

  // Early returns AFTER all hooks
  if (!sessionId) {
    return (
      <div className="container mx-auto py-8 max-w-4xl">
        <div className="text-center text-destructive">
          No session ID provided
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="container mx-auto py-8 max-w-4xl">
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mx-auto py-8 max-w-4xl">
        <div className="text-center py-12 text-destructive">
          Error loading pipeline stages: {String(error)}
        </div>
      </div>
    );
  }

  if (!stagesData) return null;

  // Steps that require validation before advancing
  const gatedSteps = new Set([2, 5]); // Initial QC and Final QC steps

  const currentStepName = steps[currentStep].name;
  const needsValidation = gatedSteps.has(currentStep) && !validatedSteps.has(currentStep);
  const isShowingComparison = qcStepsShowingComparison[currentStep] || false;

  const handleStepClick = (index: number) => {
    if (index <= maxUnlocked) {
      setCurrentStep(index);
    }
  };

  const handleShowDifference = () => {
    setQcStepsShowingComparison(prev => ({ ...prev, [currentStep]: true }));
  };

  const handleBackToParams = () => {
    setQcStepsShowingComparison(prev => ({ ...prev, [currentStep]: false }));
  };

  const handleBack = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleNext = () => {
    if (currentStep < steps.length - 1 && !needsValidation) {
      const nextStep = currentStep + 1;
      setCurrentStep(nextStep);
      setMaxUnlocked(Math.max(maxUnlocked, nextStep));
    }
  };

  const handleValidate = () => {
    setValidatedSteps(prev => new Set(prev).add(currentStep));
    // Auto-advance after validation
    handleNext();
  };

  // Render current step component
  const renderStep = () => {
    const props = {
      sessionId,
      pipelineType,
      isAutomated: isAutomated || false,
      automatedStatus,
    };

    switch (currentStepName) {
      case 'merged':
        return <LoadingStep {...props} />;
      case 'with_metadata':
        return <MetadataStep {...props} />;
      case 'initial_qc':
        return <InitialQCStep key="initial_qc" {...props} onValidate={handleValidate} showingComparison={isShowingComparison} onBackToParams={handleBackToParams} />;
      case 'corrected':
        return <CorrectionStep {...props} />;
      case 'calibrated':
        return <CalibrationStep {...props} />;
      case 'final':
        return <FinalQCStep key="final_qc" {...props} onValidate={handleValidate} showingComparison={isShowingComparison} onBackToParams={handleBackToParams} />;
      case 'production':
        return <ProductionStep {...props} />;
      default:
        return (
          <div className="text-center py-12 text-muted-foreground">
            Step "{currentStepName}" not implemented yet
          </div>
        );
    }
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b bg-background sticky top-0 z-50">
        {/* Stepper Navigation */}
        <StepperNav
          steps={steps.map((step, i) => ({
            ...step,
            validated: validatedSteps.has(i),
          }))}
          currentStep={currentStep}
          maxUnlocked={maxUnlocked}
          onStepClick={handleStepClick}
          sessionId={sessionId}
          pipelineType={pipelineType}
        />
      </div>

      {/* Automated Run Banner */}
      {isAutomated && (
        <div className={
          automatedStatus === 'needs_attention'
            ? "bg-orange-50 dark:bg-orange-950 border-b border-orange-200"
            : "bg-blue-50 dark:bg-blue-950 border-b border-blue-200"
        }>
          <div className="container mx-auto px-6 py-3 flex items-center justify-center gap-2">
            {automatedStatus === 'needs_attention' ? (
              <>
                <Edit className="h-4 w-4 text-orange-600" />
                <span className="text-sm font-medium text-orange-900 dark:text-orange-100">
                  Automated Run - Review & Fix Mode (Editing Enabled)
                </span>
              </>
            ) : (
              <>
                <Eye className="h-4 w-4 text-blue-600" />
                <span className="text-sm font-medium text-blue-900 dark:text-blue-100">
                  Automated Run - View Only Mode
                </span>
              </>
            )}
            <Badge variant="secondary" className="text-xs">
              {automatedStatus}
            </Badge>
          </div>
        </div>
      )}

      {/* Main content */}
      <div className="container mx-auto px-6 py-8 max-w-6xl">
        {renderStep()}
      </div>

      {/* Fixed bottom controls */}
      <StepperControls
        currentStep={currentStep}
        totalSteps={steps.length}
        canAdvance={!needsValidation}
        needsValidation={needsValidation}
        showingComparison={isShowingComparison}
        onBack={handleBack}
        onNext={handleNext}
        onValidate={needsValidation ? (isShowingComparison ? handleValidate : handleShowDifference) : undefined}
        onBackToParams={handleBackToParams}
      />
    </div>
  );
}
