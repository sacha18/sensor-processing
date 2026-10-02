import { useState, useEffect } from 'react';
import Plot from 'react-plotly.js';
import { Loader2 } from 'lucide-react';
import { apiClient } from '../../api/client';

interface MonthlyBoxPlotProps {
  datasetId: string;
}

export function MonthlyBoxPlot({ datasetId }: MonthlyBoxPlotProps) {
  const [data, setData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setIsLoading(true);
        const result = await apiClient.getDatasetAnalysis(datasetId, 'distribution', 10000);
        setData(result);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch distribution data:', err);
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

  if (!data || !data.distribution || data.distribution.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-sm text-muted-foreground">No data available to display</p>
      </div>
    );
  }

  // Group data by sensor_id and month
  const sensorIds = data.metadata.has_sensor_id
    ? Array.from(new Set(data.distribution.map((d: any) => d.sensor_id)))
    : ['all'];

  const traces = sensorIds.map((sensorId, idx) => {
    const sensorData = data.metadata.has_sensor_id
      ? data.distribution.filter((d: any) => d.sensor_id === sensorId)
      : data.distribution;

    return {
      x: sensorData.map((d: any) => d.month),
      y: sensorData.map((d: any) => d.value),
      type: 'box' as const,
      name: String(sensorId),
      boxpoints: 'outliers' as const,
      jitter: 0.4,
      pointpos: 0,
      marker: {
        size: 3,
        opacity: 0.35,
      },
    };
  });

  return (
    <div className="w-full">
      <Plot
        data={traces}
        layout={{
          autosize: true,
          height: 460,
          margin: { l: 60, r: 40, t: 20, b: 80 },
          xaxis: {
            title: 'Month',
            gridcolor: '#e5e7eb',
          },
          yaxis: {
            title: data.metadata.value_column || 'Value',
            gridcolor: '#e5e7eb',
          },
          boxmode: 'group',
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
