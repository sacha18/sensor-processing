import Plot from 'react-plotly.js';

interface ChannelData {
  timestamp: string[];
  values: Record<string, number[]>;
  flags?: Record<string, boolean[]>; // Optional QC flags
}

interface FacetGridChartProps {
  channels: {
    name: string;
    label: string;
    data: ChannelData;
  }[];
  height?: number;
  showLegend?: boolean;
}

export function FacetGridChart({
  channels,
  height = 800,
  showLegend = true,
}: FacetGridChartProps) {
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

  const numChannels = channels.length;
  const traces: any[] = [];

  channels.forEach((channel, channelIdx) => {
    const rowIdx = channelIdx + 1;

    // Add main line traces for each sensor
    Object.entries(channel.data.values).forEach(([sensorId, values], sensorIdx) => {
      traces.push({
        x: channel.data.timestamp,
        y: values,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: sensorId,
        line: { color: colors[sensorIdx % colors.length] },
        legendgroup: sensorId,
        showlegend: channelIdx === 0 && showLegend,
        xaxis: `x${rowIdx === 1 ? '' : rowIdx}`,
        yaxis: `y${rowIdx === 1 ? '' : rowIdx}`,
      });
    });

    // Add QC flag markers if available
    if (channel.data.flags) {
      Object.entries(channel.data.flags).forEach(([method, flagArray]) => {
        const flaggedIndices = flagArray
          .map((flag, idx) => flag ? idx : -1)
          .filter(idx => idx !== -1);

        if (flaggedIndices.length > 0) {
          const flaggedTimestamps = flaggedIndices.map(idx => channel.data.timestamp[idx]);
          const flaggedValues = flaggedIndices.map(idx =>
            Object.values(channel.data.values)[0][idx]
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
            showlegend: channelIdx === 0,
            xaxis: `x${rowIdx === 1 ? '' : rowIdx}`,
            yaxis: `y${rowIdx === 1 ? '' : rowIdx}`,
          });
        }
      });
    }
  });

  // Build layout with subplots
  const layout: any = {
    height,
    margin: { t: 40, b: 50, l: 80, r: 20 },
    grid: {
      rows: numChannels,
      columns: 1,
      pattern: 'independent',
      roworder: 'top to bottom',
    },
    showlegend: showLegend,
    legend: {
      orientation: 'h',
      yanchor: 'bottom',
      y: -0.15,
      xanchor: 'center',
      x: 0.5,
    },
    hovermode: 'closest',
    annotations: [] as any[],
  };

  // Add axis configurations for each subplot
  channels.forEach((channel, idx) => {
    const axisNum = idx + 1;
    const xAxisKey = `xaxis${axisNum === 1 ? '' : axisNum}`;
    const yAxisKey = `yaxis${axisNum === 1 ? '' : axisNum}`;

    // Calculate vertical position (top to bottom)
    const gap = 0.02; // Gap between subplots
    const plotHeight = (1.0 - gap * (numChannels - 1)) / numChannels;
    const yStart = 1.0 - (idx + 1) * plotHeight - idx * gap;
    const yEnd = 1.0 - idx * plotHeight - idx * gap;

    layout[xAxisKey] = {
      title: idx === numChannels - 1 ? 'Time' : '',
      anchor: `y${axisNum === 1 ? '' : axisNum}`,
    };

    layout[yAxisKey] = {
      title: {
        text: channel.label,
        font: { size: 14, weight: 'bold' }
      },
      domain: [yStart, yEnd],
      anchor: `x${axisNum === 1 ? '' : axisNum}`,
    };

    // Add channel label annotation on the right side
    const yMid = (yStart + yEnd) / 2;
    layout.annotations.push({
      text: `<b>${channel.label}</b>`,
      xref: 'paper',
      yref: 'paper',
      x: 1.02,
      y: yMid,
      xanchor: 'left',
      yanchor: 'middle',
      showarrow: false,
      font: { size: 16, color: '#333' },
    });
  });

  return (
    <div className="w-full">
      <Plot
        data={traces}
        layout={layout}
        config={{
          displayModeBar: true,
          displaylogo: false,
          modeBarButtonsToRemove: ['lasso2d', 'select2d'],
          toImageButtonOptions: {
            format: 'png',
            filename: 'facet_grid',
          },
        }}
        className="w-full"
        useResizeHandler
      />
    </div>
  );
}
