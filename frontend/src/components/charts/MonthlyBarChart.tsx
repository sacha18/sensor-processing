import { useState, useEffect } from 'react';
import Plot from 'react-plotly.js';
import { Loader2 } from 'lucide-react';
import { apiClient } from '../../api/client';

interface MonthlyBarChartProps {
  datasetId: string;
}

export function MonthlyBarChart({ datasetId }: MonthlyBarChartProps) {
  const [data, setData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setIsLoading(true);
        const result = await apiClient.getDatasetAnalysis(datasetId, 'monthly', 10000);
        setData(result);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch monthly data:', err);
        setError(err instanceof Error ? err.message : 'Failed to load data');
      } finally {
        setIsLoading(false);
      }
    };

    fetchData();
  }, [datasetId]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-sm text-muted-foreground">Unable to load chart: {error}</p>
      </div>
    );
  }

  if (!data || !data.monthly_stats || data.monthly_stats.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-sm text-muted-foreground">No data available to display</p>
      </div>
    );
  }

  // Group by sensor_id if available
  const sensorIds = data.metadata.has_sensor_id
    ? Array.from(new Set(data.monthly_stats.map((d: any) => d.sensor_id)))
    : ['all'];

  const traces = sensorIds.map((sensorId) => {
    const sensorData = data.metadata.has_sensor_id
      ? data.monthly_stats.filter((d: any) => d.sensor_id === sensorId)
      : data.monthly_stats;

    return {
      x: sensorData.map((d: any) => d.month),
      y: sensorData.map((d: any) => d.mean),
      type: 'bar' as const,
      name: String(sensorId),
      error_y: {
        type: 'data' as const,
        array: sensorData.map((d: any) => d.std || 0),
        visible: true,
        thickness: 1,
        width: 3,
      },
    };
  });

  return (
    <div className="w-full">
      <Plot
        data={traces}
        layout={{
          autosize: true,
          height: 420,
          margin: { l: 60, r: 40, t: 20, b: 80 },
          xaxis: {
            title: 'Month',
            gridcolor: '#e5e7eb',
          },
          yaxis: {
            title: `Mean ${data.metadata.value_column || 'Value'}`,
            gridcolor: '#e5e7eb',
          },
          barmode: 'group',
          showlegend: true,
          legend: {
            orientation: 'h',
            y: -0.25,
          },
          plot_bgcolor: '#ffffff',
          paper_bgcolor: '#ffffff',
        }}
        config={{
          responsive: true,
          displayModeBar: true,
          displaylogo: false,
          modeBarButtonsToRemove: ['lasso2d', 'select2d'],
        }}
        style={{ width: '100%' }}
        useResizeHandler={true}
      />
    </div>
  );
}
