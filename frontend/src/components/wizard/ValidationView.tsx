import { Button } from '../ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { CheckCircle } from 'lucide-react';

interface ValidationViewProps {
  beforeTitle: string;
  beforeDescription: string;
  beforeContent: React.ReactNode;
  afterTitle: string;
  afterDescription: string;
  afterContent: React.ReactNode;
  onValidate: () => void;
  validationLabel?: string;
}

export function ValidationView({
  beforeTitle,
  beforeDescription,
  beforeContent,
  afterTitle,
  afterDescription,
  afterContent,
  onValidate,
  validationLabel = "Validate & Continue"
}: ValidationViewProps) {
  return (
    <div className="space-y-6">
      {/* Before/After Grid */}
      <div className="grid grid-cols-2 gap-6">
        {/* Before (Left) */}
        <Card>
          <CardHeader>
            <CardTitle>{beforeTitle}</CardTitle>
            <CardDescription>{beforeDescription}</CardDescription>
          </CardHeader>
          <CardContent>
            {beforeContent}
          </CardContent>
        </Card>

        {/* After (Right) */}
        <Card>
          <CardHeader>
            <CardTitle>{afterTitle}</CardTitle>
            <CardDescription>{afterDescription}</CardDescription>
          </CardHeader>
          <CardContent>
            {afterContent}
          </CardContent>
        </Card>
      </div>

      {/* Validation Button */}
      <div className="flex justify-center pt-4">
        <Button
          onClick={onValidate}
          size="lg"
          className="min-w-[200px]"
        >
          <CheckCircle className="h-5 w-5 mr-2" />
          {validationLabel}
        </Button>
      </div>
    </div>
  );
}
