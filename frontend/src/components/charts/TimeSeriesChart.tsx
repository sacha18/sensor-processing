import { useState, useEffect } from 'react';
import Plot from 'react-plotly.js';
import { Loader2 } from 'lucide-react';

interface TimeSeriesChartProps {
  datasetId: string;
}

interface SensorData {
  timestamp: string[];
  values: { [sensor: string]: number[] };
}

export function TimeSeriesChart({ datasetId }: TimeSeriesChartProps) {
  const [data, setData] = useState<SensorData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setIsLoading(true);
        const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
        const response = await fetch(`${baseUrl}/api/datasets/${datasetId}/preview`);

        if (!response.ok) {
          throw new Error('Failed to fetch chart data');
        }

        const jsonData = await response.json();
        setData(jsonData);
        setError(null);
      } catch (err) {
        console.error('Chart data fetch error:', err);
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
        <div className="text-center">
          <p className="text-sm text-muted-foreground">
            Unable to load chart: {error}
          </p>
          <p className="text-xs text-muted-foreground mt-2">
            Download the dataset to view full data
          </p>
        </div>
      </div>
    );
  }

  if (!data || !data.timestamp || data.timestamp.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-sm text-muted-foreground">No data available to display</p>
      </div>
    );
  }

  // Create traces for each sensor
  const traces = Object.entries(data.values).map(([sensorId, values]) => ({
    x: data.timestamp,
    y: values,
    type: 'scatter' as const,
    mode: 'lines' as const,
    name: sensorId,
    line: { width: 2 },
  }));

  return (
    <div className="w-full">
      <Plot
        data={traces}
        layout={{
          autosize: true,
          height: 500,
          margin: { l: 60, r: 40, t: 20, b: 60 },
          xaxis: {
            title: 'Time',
            type: 'date',
            gridcolor: '#e5e7eb',
          },
          yaxis: {
            title: 'Value',
            gridcolor: '#e5e7eb',
          },
          hovermode: 'x unified',
          showlegend: true,
          legend: {
            orientation: 'h',
            y: -0.2,
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
