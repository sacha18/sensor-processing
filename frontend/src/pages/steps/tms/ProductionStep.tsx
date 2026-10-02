import { useStageData, useSessionStages, useRunSessionStage, useJobStatus, usePublishDataset } from '../../../api/hooks';
import { useAlertDialog } from '../../../hooks/useAlertDialog';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../components/ui/card';
import { Loader2, Download, CheckCircle2, Database, Info, Upload } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import { FacetGridChart } from '../../../components/charts/FacetGridChart';
import { useState, useEffect, useRef } from 'react';

interface ProductionStepProps {
  sessionId: string;
  pipelineType: string;
}

export function ProductionStep({ sessionId, pipelineType }: ProductionStepProps) {
  const { showAlert } = useAlertDialog();
  const [runningJobId, setRunningJobId] = useState<string | null>(null);
  const jobTriggeredRef = useRef(false);

  // Publish form state
  const [showPublishForm, setShowPublishForm] = useState(false);
  const [publishForm, setPublishForm] = useState({
    title: '',
    description: '',
    created_by: '',
    tags: '',
    raw_data_source: ''
  });
  const publishDataset = usePublishDataset();

  // Check which stages exist
  const { data: stagesInfo, refetch: refetchStages } = useSessionStages(sessionId, pipelineType);
  const runStage = useRunSessionStage();

  // Poll job status if running
  const { data: jobStatus } = useJobStatus(runningJobId, !!runningJobId);

  // Check if stages exist
  const finalStageExists = stagesInfo?.stages.some(s => s.base_name === 'final');
  const productionStageExists = stagesInfo?.stages.some(s => s.base_name === 'production');

  // Load stage data - only when stage exists
  const { data, isLoading, error } = useStageData(
    sessionId,
    productionStageExists ? 'production' : null,
    pipelineType,
    1000
  );

  // Auto-trigger production job if final exists but production doesn't
  useEffect(() => {
    if (stagesInfo && finalStageExists && !productionStageExists && !runningJobId && !jobTriggeredRef.current) {
      console.log('Production stage not found, triggering job...');
      jobTriggeredRef.current = true;
      runStage.mutateAsync({
        sessionId,
        stageName: 'production',
        pipelineType
      }).then(result => {
        console.log('Production job started:', result.job_id);
        setRunningJobId(result.job_id);
      }).catch(error => {
        console.error('Failed to start production job:', error);
        jobTriggeredRef.current = false;
      });
    }
  }, [stagesInfo, finalStageExists, productionStageExists, runningJobId, sessionId, pipelineType, runStage]);

  // When job completes, refetch stages list
  useEffect(() => {
    if (jobStatus?.status === 'finished') {
      console.log('Production job completed, refetching stages...');
      setRunningJobId(null);
      jobTriggeredRef.current = false;
      refetchStages();
    }
  }, [jobStatus?.status, refetchStages]);

  // Show loading/job progress
  if (!stagesInfo || runningJobId || isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-12 gap-4">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        {jobStatus && (
          <div className="text-center">
            <p className="text-sm font-medium">{jobStatus.message || 'Processing...'}</p>
            <p className="text-xs text-muted-foreground mt-1">
              {jobStatus.current_stage}
            </p>
            {jobStatus.progress > 0 && (
              <div className="mt-3 w-64 bg-muted rounded-full h-2">
                <div
                  className="bg-primary h-2 rounded-full transition-all"
                  style={{ width: `${jobStatus.progress}%` }}
                />
              </div>
            )}
          </div>
        )}
        {!jobStatus && <p className="text-sm text-muted-foreground">Loading production data...</p>}
      </div>
    );
  }

  // Waiting for final stage
  if (!finalStageExists) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Info className="h-12 w-12 mx-auto mb-4" />
        <p>Please complete the Final QC step first</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12 text-destructive">
        Error loading production data: {String(error)}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        No production data available yet
      </div>
    );
  }

  const uniqueSensors = new Set(data.data.map((row: any) => row.sensor_id)).size;

  return (
    <div className="space-y-6 pb-24">
      <div>
        <h2 className="text-2xl font-bold mb-2">Production Dataset</h2>
        <p className="text-muted-foreground">
          Final cleaned and processed dataset ready for analysis
        </p>
      </div>

      {/* Success metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="border-green-200 bg-green-50 dark:bg-green-950">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Pipeline Complete</CardTitle>
            <CheckCircle2 className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-700">Success</div>
            <p className="text-xs text-green-600">
              All processing stages completed
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Final Row Count</CardTitle>
            <Database className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{data.total_rows.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">
              cleaned observations
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Sensors</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{uniqueSensors}</div>
            <p className="text-xs text-muted-foreground">
              in final dataset
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Final data visualization - VWC by sensor */}
      {data.data.length > 0 && (() => {
        // Get unique sensors
        const sensorIds = [...new Set(data.data.map((row: any) => row.sensor_id))].sort();

        // Prepare data for each sensor as a separate facet
        const channels = sensorIds.map(sensorId => {
          const sensorData = data.data.filter((row: any) => row.sensor_id === sensorId);
          const timestamps = sensorData.map((row: any) => row.timestamp);
          const vwcValues = sensorData.map((row: any) => row.vwc_final ?? null);

          return {
            name: String(sensorId),
            label: String(sensorId),
            data: {
              timestamp: timestamps,
              values: {
                [String(sensorId)]: vwcValues
              }
            }
          };
        });

        return (
          <Card>
            <CardHeader>
              <CardTitle>VWC (final) - All Sensors</CardTitle>
              <CardDescription>
                Final volumetric water content after all quality control stages ({data.sampled_rows} sampled points per sensor)
              </CardDescription>
            </CardHeader>
            <CardContent>
              <FacetGridChart
                channels={channels}
                height={200 * sensorIds.length}
                showLegend={false}
              />
            </CardContent>
          </Card>
        );
      })()}

      {/* Next steps */}
      <Card>
        <CardHeader>
          <CardTitle>Next Steps</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="h-5 w-5 text-green-500 mt-0.5" />
            <div>
              <p className="font-medium">Pipeline completed successfully</p>
              <p className="text-sm text-muted-foreground">
                All {uniqueSensors} sensors processed through all QC stages
              </p>
            </div>
          </div>

          <div className="flex items-start gap-3">
            <Download className="h-5 w-5 text-blue-500 mt-0.5" />
            <div>
              <p className="font-medium">Ready to publish</p>
              <p className="text-sm text-muted-foreground">
                Return to the job status page to publish this dataset with metadata and tags
              </p>
            </div>
          </div>

          <div className="pt-4 flex gap-3">
            <Button
              onClick={() => setShowPublishForm(!showPublishForm)}
              className="flex-1"
            >
              <Upload className="h-4 w-4 mr-2" />
              {showPublishForm ? 'Cancel' : 'Publish Dataset'}
            </Button>
            <Button
              onClick={() => window.history.back()}
              variant="outline"
            >
              Return to Job Status
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Publish Dataset Form */}
      {showPublishForm && (
        <Card>
          <CardHeader>
            <CardTitle>Publish Dataset</CardTitle>
            <CardDescription>
              Save this processed dataset for future analysis and sharing
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={async (e) => {
              e.preventDefault();
              try {
                await publishDataset.mutateAsync({
                  session_id: sessionId,
                  pipeline_type: pipelineType,
                  title: publishForm.title,
                  description: publishForm.description || undefined,
                  created_by: publishForm.created_by,
                  tags: publishForm.tags ? publishForm.tags.split(',').map(t => t.trim()) : undefined,
                  raw_data_source: publishForm.raw_data_source || undefined,
                });
                showAlert({
                  variant: 'success',
                  message: 'Dataset published successfully!',
                });
                setShowPublishForm(false);
                setPublishForm({ title: '', description: '', created_by: '', tags: '', raw_data_source: '' });
              } catch (error) {
                showAlert({
                  variant: 'error',
                  message: 'Failed to publish dataset: ' + String(error),
                });
              }
            }} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="title">Title *</Label>
                <Input
                  id="title"
                  value={publishForm.title}
                  onChange={(e) => setPublishForm({ ...publishForm, title: e.target.value })}
                  placeholder="e.g., TMS Soil Moisture - Spring 2024"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  value={publishForm.description}
                  onChange={(e) => setPublishForm({ ...publishForm, description: e.target.value })}
                  placeholder="Optional: describe the dataset, methodology, site info..."
                  rows={3}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="created_by">Your Name *</Label>
                <Input
                  id="created_by"
                  value={publishForm.created_by}
                  onChange={(e) => setPublishForm({ ...publishForm, created_by: e.target.value })}
                  placeholder="e.g., J. Smith"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="tags">Tags</Label>
                <Input
                  id="tags"
                  value={publishForm.tags}
                  onChange={(e) => setPublishForm({ ...publishForm, tags: e.target.value })}
                  placeholder="comma-separated, e.g., soil-moisture, agroforestry, 2024"
                />
                <p className="text-xs text-muted-foreground">
                  Comma-separated keywords for easier searching
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="raw_data_source">Raw Data Source</Label>
                <Input
                  id="raw_data_source"
                  value={publishForm.raw_data_source}
                  onChange={(e) => setPublishForm({ ...publishForm, raw_data_source: e.target.value })}
                  placeholder="e.g., field campaign ID, download link..."
                />
              </div>

              <div className="flex gap-3 pt-2">
                <Button type="submit" disabled={publishDataset.isPending} className="flex-1">
                  {publishDataset.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Publishing...
                    </>
                  ) : (
                    <>
                      <Upload className="h-4 w-4 mr-2" />
                      Publish
                    </>
                  )}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setShowPublishForm(false)}
                >
                  Cancel
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
