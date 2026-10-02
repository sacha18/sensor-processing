import { useParams, Link, useNavigate } from 'react-router-dom';
import { useDataset, useArchiveDataset } from '../api/hooks';
import { apiClient } from '../api/client';
import { useAlertDialog } from '../hooks/useAlertDialog';
import { useConfirmDialog } from '../hooks/useConfirmDialog';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { TimeSeriesChart } from '../components/charts/TimeSeriesChart';
import { DailyStatsChart } from '../components/charts/DailyStatsChart';
import { MonthlyBoxPlot } from '../components/charts/MonthlyBoxPlot';
import { MonthlyBarChart } from '../components/charts/MonthlyBarChart';
import { SummaryStatsTable } from '../components/charts/SummaryStatsTable';
import {
  ArrowLeft,
  Download,
  Trash2,
  Calendar,
  User,
  Database,
  FileCode,
  Loader2,
} from 'lucide-react';

export function DatasetDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: dataset, isLoading, error } = useDataset(id || null);
  const archiveMutation = useArchiveDataset();
  const { showAlert } = useAlertDialog();
  const { confirm } = useConfirmDialog();

  const handleDownload = () => {
    if (!id) return;
    apiClient.downloadDataset(id, `${dataset?.title || 'dataset'}.parquet`);
  };

  const handleArchive = async () => {
    if (!id) return;

    const confirmed = await confirm({
      title: 'Archive Dataset',
      message: 'Archive this dataset? It will be hidden from the main list.',
      confirmText: 'Archive',
      variant: 'destructive',
    });

    if (!confirmed) return;

    try {
      await archiveMutation.mutateAsync(id);
      navigate('/');
    } catch (error) {
      console.error('Failed to archive dataset:', error);
      showAlert({
        variant: 'error',
        message: 'Failed to archive dataset',
      });
    }
  };

  if (isLoading) {
    return (
      <div className="container mx-auto py-8 max-w-6xl">
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </div>
    );
  }

  if (error || !dataset) {
    return (
      <div className="container mx-auto py-8 max-w-6xl">
        <Card>
          <CardHeader>
            <CardTitle>Dataset Not Found</CardTitle>
            <CardDescription>
              The dataset you're looking for doesn't exist or has been archived.
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  return (
    <div className="container mx-auto py-8 max-w-6xl">
      {/* Header */}
      <div className="mb-6">
        <Link
          to="/"
          className="text-sm text-muted-foreground hover:underline flex items-center gap-1 mb-2"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Browse
        </Link>
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-3xl font-bold mb-2">{dataset.title}</h1>
            {dataset.description && (
              <p className="text-muted-foreground">{dataset.description}</p>
            )}
          </div>
          <div className="flex gap-2">
            <Button onClick={handleDownload} variant="outline">
              <Download className="h-4 w-4 mr-2" />
              Download
            </Button>
            <Button
              onClick={handleArchive}
              variant="destructive"
              disabled={archiveMutation.isPending}
            >
              <Trash2 className="h-4 w-4 mr-2" />
              Archive
            </Button>
          </div>
        </div>
      </div>

      <div className="grid gap-6">
        {/* Metadata Card */}
        <Card>
          <CardHeader>
            <CardTitle>Dataset Information</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                  <User className="h-4 w-4" />
                  Created By
                </div>
                <p className="font-medium">{dataset.created_by}</p>
              </div>

              <div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                  <Calendar className="h-4 w-4" />
                  Created
                </div>
                <p className="font-medium">
                  {new Date(dataset.created_at).toLocaleDateString()}
                </p>
              </div>

              <div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                  <Database className="h-4 w-4" />
                  Pipeline Type
                </div>
                <Badge>{dataset.pipeline_type.toUpperCase()}</Badge>
              </div>

              <div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                  <FileCode className="h-4 w-4" />
                  Format
                </div>
                <p className="font-medium">Parquet</p>
              </div>
            </div>

            <div className="mt-6 grid grid-cols-2 md:grid-cols-3 gap-4 pt-4 border-t">
              <div>
                <p className="text-sm text-muted-foreground">Rows</p>
                <p className="text-2xl font-bold">{dataset.row_count?.toLocaleString()}</p>
              </div>

              <div>
                <p className="text-sm text-muted-foreground">Sensors</p>
                <p className="text-2xl font-bold">{dataset.sensor_count}</p>
              </div>

              {dataset.date_range_start && dataset.date_range_end && (
                <div className="col-span-2 md:col-span-1">
                  <p className="text-sm text-muted-foreground">Date Range</p>
                  <p className="text-sm font-medium">
                    {new Date(dataset.date_range_start).toLocaleDateString()} →{' '}
                    {new Date(dataset.date_range_end).toLocaleDateString()}
                  </p>
                </div>
              )}
            </div>

            {dataset.tags && dataset.tags.length > 0 && (
              <div className="mt-4 pt-4 border-t">
                <p className="text-sm text-muted-foreground mb-2">Tags</p>
                <div className="flex flex-wrap gap-2">
                  {dataset.tags.map((tag) => (
                    <Badge key={tag} variant="outline">
                      {tag}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Analysis Visualizations */}
        <Card>
          <CardHeader>
            <CardTitle>Dataset Analysis</CardTitle>
            <CardDescription>
              Interactive charts and statistics for exploring sensor data
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="overview" className="w-full">
              <TabsList className="grid w-full grid-cols-5">
                <TabsTrigger value="overview">Overview</TabsTrigger>
                <TabsTrigger value="daily">Daily Trends</TabsTrigger>
                <TabsTrigger value="monthly">Monthly Stats</TabsTrigger>
                <TabsTrigger value="distribution">Distribution</TabsTrigger>
                <TabsTrigger value="summary">Summary</TabsTrigger>
              </TabsList>

              <TabsContent value="overview" className="mt-4">
                <div className="space-y-4">
                  <div>
                    <h3 className="text-lg font-semibold mb-2">Time Series Overview</h3>
                    <p className="text-sm text-muted-foreground mb-4">
                      Raw sensor readings over time (sampled for performance)
                    </p>
                    <TimeSeriesChart datasetId={dataset.dataset_id} />
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="daily" className="mt-4">
                <div className="space-y-4">
                  <div>
                    <h3 className="text-lg font-semibold mb-2">Daily Statistics</h3>
                    <p className="text-sm text-muted-foreground mb-4">
                      Daily aggregated values with individual sensors (thin lines) and group means (thick lines).
                      Hover over lines to see sample size (n).
                    </p>
                    <DailyStatsChart datasetId={dataset.dataset_id} />
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="monthly" className="mt-4">
                <div className="space-y-6">
                  <div>
                    <h3 className="text-lg font-semibold mb-2">Monthly Distribution (Box Plots)</h3>
                    <p className="text-sm text-muted-foreground mb-4">
                      Distribution of values for each month, grouped by sensor.
                      Shows outliers, quartiles, and median values.
                    </p>
                    <MonthlyBoxPlot datasetId={dataset.dataset_id} />
                  </div>

                  <div className="pt-6 border-t">
                    <h3 className="text-lg font-semibold mb-2">Monthly Mean (Bar Chart)</h3>
                    <p className="text-sm text-muted-foreground mb-4">
                      Mean value per month with error bars showing standard deviation.
                    </p>
                    <MonthlyBarChart datasetId={dataset.dataset_id} />
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="distribution" className="mt-4">
                <div className="space-y-4">
                  <div>
                    <h3 className="text-lg font-semibold mb-2">Value Distribution</h3>
                    <p className="text-sm text-muted-foreground mb-4">
                      Box plots showing the distribution of sensor values across months.
                    </p>
                    <MonthlyBoxPlot datasetId={dataset.dataset_id} />
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="summary" className="mt-4">
                <div className="space-y-4">
                  <div>
                    <h3 className="text-lg font-semibold mb-2">Summary Statistics</h3>
                    <p className="text-sm text-muted-foreground mb-4">
                      Statistical summary by sensor and group: count, mean, std dev, quartiles, min/max.
                    </p>
                    <SummaryStatsTable datasetId={dataset.dataset_id} />
                  </div>
                </div>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>

        {/* Technical Details */}
        <Card>
          <CardHeader>
            <CardTitle>Technical Details</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-muted-foreground">Dataset ID:</span>
                <p className="font-mono text-xs mt-1">{dataset.dataset_id}</p>
              </div>
              {dataset.raw_data_source && (
                <div>
                  <span className="text-muted-foreground">Source Files:</span>
                  <p className="font-mono text-xs mt-1">{dataset.raw_data_source}</p>
                </div>
              )}
              <div>
                <span className="text-muted-foreground">Checksum (SHA256):</span>
                <p className="font-mono text-xs mt-1 truncate">
                  {dataset.output_checksum}
                </p>
              </div>
              <div>
                <span className="text-muted-foreground">Storage Path:</span>
                <p className="font-mono text-xs mt-1 truncate">{dataset.output_path}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
