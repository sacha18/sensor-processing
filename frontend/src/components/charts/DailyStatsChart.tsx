import { useState, useEffect } from 'react';
import Plot from 'react-plotly.js';
import { Loader2 } from 'lucide-react';
import { apiClient } from '../../api/client';

interface DailyStatsChartProps {
  datasetId: string;
}

export function DailyStatsChart({ datasetId }: DailyStatsChartProps) {
  const [data, setData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setIsLoading(true);
        const result = await apiClient.getDatasetAnalysis(datasetId, 'daily', 10000);
        setData(result);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch daily data:', err);
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

  if (!data || !data.per_sensor || data.per_sensor.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-sm text-muted-foreground">No data available to display</p>
      </div>
    );
  }

  const traces: any[] = [];

  // Add individual sensor traces (thin, semi-transparent)
  if (data.metadata.has_sensor_id) {
    const sensorIds = Array.from(new Set(data.per_sensor.map((d: any) => d.sensor_id)));

    sensorIds.forEach((sensorId, idx) => {
      const sensorData = data.per_sensor.filter((d: any) => d.sensor_id === sensorId);

      traces.push({
        x: sensorData.map((d: any) => d.date),
        y: sensorData.map((d: any) => d.mean),
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: `${sensorId} (sensor)`,
        line: {
          color: `hsl(${(idx * 360) / sensorIds.length}, 70%, 50%)`,
          width: 1,
        },
        opacity: 0.28,
        showlegend: false,
        hoverinfo: 'skip' as const,
      });
    });
  }

  // Add group mean traces (thick lines)
  if (data.group_means && data.group_means.length > 0) {
    const groupKeys = data.metadata.group_columns || [];

    // Group by the combination of group columns
    const groups = new Map<string, any[]>();
    data.group_means.forEach((row: any) => {
      const key = groupKeys.map(col => row[col] || 'unset').join('|');
      if (!groups.has(key)) {
        groups.set(key, []);
      }
      groups.get(key)!.push(row);
    });

    let idx = 0;
    groups.forEach((groupData, groupKey) => {
      traces.push({
        x: groupData.map((d: any) => d.date),
        y: groupData.map((d: any) => d.group_mean),
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: groupKey.replace(/\|/g, ' | '),
        line: {
          color: `hsl(${(idx * 360) / groups.size}, 70%, 50%)`,
          width: 2.5,
        },
        customdata: groupData.map((d: any) => d.n_sensors),
        hovertemplate: `%{x}<br>%{y:.3f}<br>Sensors: %{customdata}<extra></extra>`,
      });
      idx++;
    });
  } else if (!data.metadata.has_sensor_id) {
    // No sensor_id, just plot the aggregated data
    traces.push({
      x: data.per_sensor.map((d: any) => d.date),
      y: data.per_sensor.map((d: any) => d.mean),
      type: 'scatter' as const,
      mode: 'lines' as const,
      name: 'Daily Mean',
      line: { width: 2.5 },
      customdata: data.per_sensor.map((d: any) => d.n),
      hovertemplate: '%{x}<br>%{y:.3f}<br>Observations: %{customdata}<extra></extra>',
    });
  }

  return (
    <div className="w-full">
      <Plot
        data={traces}
        layout={{
          autosize: true,
          height: 500,
          margin: { l: 60, r: 40, t: 20, b: 60 },
          xaxis: {
            title: 'Date',
            type: 'date',
            gridcolor: '#e5e7eb',
          },
          yaxis: {
            title: `Daily Mean ${data.metadata.value_column || 'Value'}`,
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
