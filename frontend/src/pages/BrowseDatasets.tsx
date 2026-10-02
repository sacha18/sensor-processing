import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useDatasets } from '../api/hooks';
import { apiClient } from '../api/client';
import { useAlertDialog } from '../hooks/useAlertDialog';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Download, FileCode, Calendar, User, Database, Eye } from 'lucide-react';

export function BrowseDatasets() {
  const [search, setSearch] = useState('');
  const [pipelineFilter, setPipelineFilter] = useState<string>('');
  const { showAlert } = useAlertDialog();

  const { data, isLoading, error } = useDatasets({
    search: search || undefined,
    pipeline_type: pipelineFilter || undefined,
    limit: 50,
  });

  const handleDownload = async (datasetId: string, title: string) => {
    try {
      await apiClient.downloadDataset(datasetId, `${title}.parquet`);
    } catch (err) {
      console.error('Download failed:', err);
      showAlert({
        variant: 'error',
        message: 'Failed to download dataset',
      });
    }
  };

  return (
    <div className="container mx-auto py-8 px-4 max-w-7xl">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold mb-2">Published Datasets</h1>
        <p className="text-muted-foreground">
          Browse and download sensor data processing results
        </p>
      </div>

      {/* Filters */}
      <div className="flex gap-4 mb-6">
        <div className="flex-1">
          <Input
            placeholder="🔍 Search by title..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <select
          className="h-10 rounded-md border border-input bg-background px-3 py-2 text-sm"
          value={pipelineFilter}
          onChange={(e) => setPipelineFilter(e.target.value)}
        >
          <option value="">All Pipelines</option>
          <option value="tms">TMS</option>
        </select>
      </div>

      {/* Loading/Error States */}
      {isLoading && (
        <div className="text-center py-12">
          <div className="animate-pulse">Loading datasets...</div>
        </div>
      )}

      {error && (
        <div className="text-center py-12 text-destructive">
          <p>Error loading datasets: {(error as Error).message}</p>
        </div>
      )}

      {/* Dataset Grid */}
      {data && (
        <>
          <div className="mb-4 text-sm text-muted-foreground">
            Found {data.total} dataset{data.total !== 1 ? 's' : ''}
          </div>

          {data.datasets.length === 0 ? (
            <Card>
              <CardContent className="text-center py-12">
                <p className="text-muted-foreground">No datasets found</p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-4">
              {data.datasets.map((dataset) => (
                <Card key={dataset.dataset_id} className="hover:shadow-md transition-shadow">
                  <CardHeader>
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <CardTitle className="mb-2">{dataset.title}</CardTitle>
                        <CardDescription>
                          {dataset.description || 'No description provided'}
                        </CardDescription>
                      </div>
                      <Badge variant="secondary">
                        {dataset.pipeline_type}
                      </Badge>
                    </div>
                  </CardHeader>

                  <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4 text-sm">
                      <div className="flex items-center gap-2">
                        <User className="w-4 h-4 text-muted-foreground" />
                        <span className="text-muted-foreground">
                          {dataset.created_by}
                        </span>
                      </div>

                      <div className="flex items-center gap-2">
                        <Calendar className="w-4 h-4 text-muted-foreground" />
                        <span className="text-muted-foreground">
                          {new Date(dataset.created_at).toLocaleDateString()}
                        </span>
                      </div>

                      {dataset.sensor_count && (
                        <div className="flex items-center gap-2">
                          <Database className="w-4 h-4 text-muted-foreground" />
                          <span className="text-muted-foreground">
                            {dataset.sensor_count} sensor{dataset.sensor_count !== 1 ? 's' : ''}
                          </span>
                        </div>
                      )}

                      {dataset.row_count && (
                        <div className="flex items-center gap-2">
                          <FileCode className="w-4 h-4 text-muted-foreground" />
                          <span className="text-muted-foreground">
                            {dataset.row_count.toLocaleString()} rows
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Tags */}
                    {dataset.tags.length > 0 && (
                      <div className="flex gap-2 flex-wrap mb-4">
                        {dataset.tags.map((tag) => (
                          <Badge key={tag} variant="outline">
                            {tag}
                          </Badge>
                        ))}
                      </div>
                    )}

                    {/* Date Range */}
                    {dataset.date_range_start && dataset.date_range_end && (
                      <div className="text-sm text-muted-foreground mb-4">
                        <span className="font-medium">Data range:</span>{' '}
                        {new Date(dataset.date_range_start).toLocaleDateString()} →{' '}
                        {new Date(dataset.date_range_end).toLocaleDateString()}
                      </div>
                    )}

                    {/* Actions */}
                    <div className="flex gap-2">
                      <Link to={`/datasets/${dataset.dataset_id}`}>
                        <Button size="sm" variant="default">
                          <Eye className="w-4 h-4 mr-2" />
                          View Details
                        </Button>
                      </Link>

                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleDownload(dataset.dataset_id, dataset.title)}
                      >
                        <Download className="w-4 h-4 mr-2" />
                        Download
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
