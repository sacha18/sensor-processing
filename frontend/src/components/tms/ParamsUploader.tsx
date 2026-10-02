import { useState } from 'react';
import { Upload, FileText, HelpCircle } from 'lucide-react';
import { Button } from '../ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Alert, AlertDescription } from '../ui/alert';

interface ParamsUploaderProps {
  title: string;
  description: string;
  exampleFormat: {
    columns: string;
    csvExample: string;
    jsonExample?: string;
  };
  onUpload: (file: File) => Promise<{ success: boolean; message: string; rowsAdded?: number }>;
}

export function ParamsUploader({ title, description, exampleFormat, onUpload }: ParamsUploaderProps) {
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{ success: boolean; message: string } | null>(null);
  const [showExample, setShowExample] = useState(false);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setUploadResult(null);

    try {
      const result = await onUpload(file);
      setUploadResult(result);
    } catch (error) {
      setUploadResult({
        success: false,
        message: `Upload failed: ${String(error)}`
      });
    } finally {
      setUploading(false);
      // Reset input
      e.target.value = '';
    }
  };

  const downloadExample = (type: 'csv' | 'json') => {
    const content = type === 'csv' ? exampleFormat.csvExample : exampleFormat.jsonExample || '';
    const blob = new Blob([content], { type: type === 'csv' ? 'text/csv' : 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${title.toLowerCase().replace(/\s+/g, '_')}_example.${type}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <div>
        <label htmlFor="file-upload" className="block text-sm font-medium mb-2">
          {title}
        </label>
        <div className="flex items-center gap-2">
          <label
            htmlFor="file-upload"
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 border border-dashed rounded-lg cursor-pointer hover:border-primary hover:bg-accent transition-colors"
          >
            <Upload className="h-4 w-4" />
            <span className="text-sm">{uploading ? 'Uploading...' : 'Choose CSV or JSON file'}</span>
            <input
              id="file-upload"
              type="file"
              accept=".csv,.json"
              onChange={handleFileChange}
              disabled={uploading}
              className="hidden"
            />
          </label>
          <Button
            variant="outline"
            size="icon"
            onClick={() => setShowExample(!showExample)}
            title="Show example format"
          >
            <HelpCircle className="h-4 w-4" />
          </Button>
        </div>
        <p className="text-xs text-muted-foreground mt-1">{description}</p>
      </div>

      {uploadResult && (
        <Alert variant={uploadResult.success ? 'default' : 'destructive'}>
          <AlertDescription>{uploadResult.message}</AlertDescription>
        </Alert>
      )}

      {showExample && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm flex items-center gap-2">
              <FileText className="h-4 w-4" />
              Example File Format
            </CardTitle>
            <CardDescription className="text-xs">
              Columns: {exampleFormat.columns}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium">CSV Example</span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => downloadExample('csv')}
                >
                  Download CSV
                </Button>
              </div>
              <pre className="text-xs bg-muted p-3 rounded-lg overflow-x-auto">
                {exampleFormat.csvExample}
              </pre>
            </div>
            {exampleFormat.jsonExample && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium">JSON Example</span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => downloadExample('json')}
                  >
                    Download JSON
                  </Button>
                </div>
                <pre className="text-xs bg-muted p-3 rounded-lg overflow-x-auto">
                  {exampleFormat.jsonExample}
                </pre>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
