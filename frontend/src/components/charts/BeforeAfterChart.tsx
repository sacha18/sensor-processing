import Plot from 'react-plotly.js';

interface BeforeAfterChartProps {
  beforeData: {
    timestamp: string[];
    values: Record<string, number[]>;
    flags?: Record<string, boolean[]>; // Optional QC flags for before data
  };
  afterData: {
    timestamp: string[];
    values: Record<string, number[]>;
    flags?: Record<string, boolean[]>; // Optional QC flags for after data
  };
  beforeTitle?: string;
  afterTitle?: string;
  yAxisLabel?: string;
  height?: number;
}

export function BeforeAfterChart({
  beforeData,
  afterData,
  beforeTitle = 'Before',
  afterTitle = 'After',
  yAxisLabel = 'Value',
  height = 400,
}: BeforeAfterChartProps) {
  const colors = [
    '#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de',
    '#3ba272', '#fc8452', '#9a60b4', '#ea7ccc'
  ];

  const qcColors = {
    // Initial QC methods
    hampel: '#ee6666',
    flatline: '#fac858',
    range: '#fc8452',
    rate: '#9a60b4',
    // Final QC methods
    vwc_range: '#fc8452',
    freezing: '#5470c6',
    vwc_flatline: '#fac858',
    field_event: '#ee6666',
    cross_channel: '#9a60b4',
  };

  const traces: any[] = [];

  // Create traces for "Before" subplot
  Object.entries(beforeData.values).forEach(([sensorId, values], idx) => {
    traces.push({
      x: beforeData.timestamp,
      y: values,
      type: 'scatter' as const,
      mode: 'lines' as const,
      name: sensorId,
      line: { color: colors[idx % colors.length] },
      legendgroup: sensorId,
      showlegend: true,
      xaxis: 'x',
      yaxis: 'y',
    });
  });

  // Add QC flag markers for "Before" if available
  if (beforeData.flags) {
    Object.entries(beforeData.flags).forEach(([method, flagArray]) => {
      const flaggedIndices = flagArray
        .map((flag, idx) => flag ? idx : -1)
        .filter(idx => idx !== -1);

      if (flaggedIndices.length > 0) {
        const flaggedTimestamps = flaggedIndices.map(idx => beforeData.timestamp[idx]);
        const flaggedValues = flaggedIndices.map(idx =>
          Object.values(beforeData.values)[0][idx]
        );

        traces.push({
          x: flaggedTimestamps,
          y: flaggedValues,
          type: 'scatter' as const,
          mode: 'markers' as const,
          name: method,
          marker: {
            color: qcColors[method as keyof typeof qcColors] || '#999',
            size: 8,
            line: { width: 1, color: 'white' }
          },
          legendgroup: method,
          showlegend: true,
          xaxis: 'x',
          yaxis: 'y',
        });
      }
    });
  }

  // Create traces for "After" subplot
  Object.entries(afterData.values).forEach(([sensorId, values], idx) => {
    traces.push({
      x: afterData.timestamp,
      y: values,
      type: 'scatter' as const,
      mode: 'lines' as const,
      name: sensorId,
      line: { color: colors[idx % colors.length] },
      legendgroup: sensorId,
      showlegend: false,
      xaxis: 'x2',
      yaxis: 'y2',
    });
  });

  // Add QC flag markers for "After" if available
  if (afterData.flags) {
    Object.entries(afterData.flags).forEach(([method, flagArray]) => {
      const flaggedIndices = flagArray
        .map((flag, idx) => flag ? idx : -1)
        .filter(idx => idx !== -1);

      if (flaggedIndices.length > 0) {
        const flaggedTimestamps = flaggedIndices.map(idx => afterData.timestamp[idx]);
        const flaggedValues = flaggedIndices.map(idx =>
          Object.values(afterData.values)[0][idx]
        );

        traces.push({
          x: flaggedTimestamps,
          y: flaggedValues,
          type: 'scatter' as const,
          mode: 'markers' as const,
          name: method,
          marker: {
            color: qcColors[method as keyof typeof qcColors] || '#999',
            size: 8,
            line: { width: 1, color: 'white' }
          },
          legendgroup: method,
          showlegend: false,
          xaxis: 'x2',
          yaxis: 'y2',
        });
      }
    });
  }

  return (
    <div className="w-full">
      <Plot
        data={traces}
        layout={{
          height,
          margin: { t: 30, b: 50, l: 60, r: 60 },
          grid: {
            rows: 1,
            columns: 2,
            pattern: 'independent',
            roworder: 'top to bottom',
          },
          xaxis: {
            title: beforeTitle,
            domain: [0, 0.48],
          },
          yaxis: {
            title: yAxisLabel,
            anchor: 'x',
          },
          xaxis2: {
            title: afterTitle,
            domain: [0.52, 1],
          },
          yaxis2: {
            title: yAxisLabel,
            anchor: 'x2',
          },
          legend: {
            orientation: 'h',
            yanchor: 'bottom',
            y: -0.3,
            xanchor: 'center',
            x: 0.5,
          },
          hovermode: 'closest',
        }}
        config={{
          displayModeBar: true,
          displaylogo: false,
          modeBarButtonsToRemove: ['lasso2d', 'select2d'],
          toImageButtonOptions: {
            format: 'png',
            filename: 'before_after_comparison',
          },
        }}
        className="w-full"
        useResizeHandler
      />
    </div>
  );
}
