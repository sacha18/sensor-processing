import { ReactNode } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Loader2, Save } from 'lucide-react';

export interface ParametersSidebarProps {
  title: string;
  description: string;
  icon?: ReactNode;
  children: ReactNode;
  hasUnsavedChanges: boolean;
  isApplying: boolean;
  onApply: () => void;
  applyButtonText?: string;
}

/**
 * Generic sticky sidebar for parameters across all pipeline steps.
 * Provides consistent styling and behavior for parameter editing UI.
 *
 * Usage:
 * <ParametersSidebar
 *   title="Initial QC Parameters"
 *   description="Per-channel quality control settings"
 *   icon={<Shield />}
 *   hasUnsavedChanges={hasChanges}
 *   isApplying={isApplying}
 *   onApply={handleApply}
 * >
 *   <YourParameterControls />
 * </ParametersSidebar>
 */
export function ParametersSidebar({
  title,
  description,
  icon,
  children,
  hasUnsavedChanges,
  isApplying,
  onApply,
  applyButtonText = 'Apply Changes'
}: ParametersSidebarProps) {
  return (
    <div className="w-80 flex-shrink-0 space-y-4 sticky top-20 self-start">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {icon}
            {title}
          </CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {children}

          {/* Apply Changes Button */}
          <Button
            onClick={onApply}
            disabled={!hasUnsavedChanges || isApplying}
            className="w-full"
          >
            {isApplying ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Applying...
              </>
            ) : (
              <>
                <Save className="mr-2 h-4 w-4" />
                {applyButtonText}
              </>
            )}
          </Button>
          {hasUnsavedChanges && (
            <p className="text-xs text-orange-600">
              You have unsaved changes
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
