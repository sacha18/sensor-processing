import { useState, useEffect } from 'react';
import { Loader2 } from 'lucide-react';
import { apiClient } from '../../api/client';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../ui/table';

interface SummaryStatsTableProps {
  datasetId: string;
}

export function SummaryStatsTable({ datasetId }: SummaryStatsTableProps) {
  const [data, setData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setIsLoading(true);
        const result = await apiClient.getDatasetAnalysis(datasetId, 'summary', 1000);
        setData(result);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch summary stats:', err);
        setError(err instanceof Error ? err.message : 'Failed to load data');
      } finally {
        setIsLoading(false);
      }
    };

    fetchData();
  }, [datasetId]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-8">
        <p className="text-sm text-muted-foreground">Unable to load summary: {error}</p>
      </div>
    );
  }

  if (!data || !data.summary || data.summary.length === 0) {
    return (
      <div className="flex items-center justify-center py-8">
        <p className="text-sm text-muted-foreground">No summary data available</p>
      </div>
    );
  }

  const formatNumber = (val: number | null | undefined) => {
    if (val === null || val === undefined) return 'N/A';
    return val.toFixed(3);
  };

  return (
    <div className="w-full overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            {data.metadata.has_sensor_id && <TableHead>Sensor ID</TableHead>}
            {data.metadata.group_columns?.map((col: string) => (
              <TableHead key={col}>{col}</TableHead>
            ))}
            <TableHead className="text-right">Count</TableHead>
            <TableHead className="text-right">Mean</TableHead>
            <TableHead className="text-right">Std Dev</TableHead>
            <TableHead className="text-right">Min</TableHead>
            <TableHead className="text-right">Q25</TableHead>
            <TableHead className="text-right">Median</TableHead>
            <TableHead className="text-right">Q75</TableHead>
            <TableHead className="text-right">Max</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.summary.map((row: any, idx: number) => (
            <TableRow key={idx}>
              {data.metadata.has_sensor_id && (
                <TableCell className="font-medium">{row.sensor_id}</TableCell>
              )}
              {data.metadata.group_columns?.map((col: string) => (
                <TableCell key={col}>{row[col] || '—'}</TableCell>
              ))}
              <TableCell className="text-right">{row.count?.toLocaleString()}</TableCell>
              <TableCell className="text-right">{formatNumber(row.mean)}</TableCell>
              <TableCell className="text-right">{formatNumber(row.std)}</TableCell>
              <TableCell className="text-right">{formatNumber(row.min)}</TableCell>
              <TableCell className="text-right">{formatNumber(row.q25)}</TableCell>
              <TableCell className="text-right">{formatNumber(row.median)}</TableCell>
              <TableCell className="text-right">{formatNumber(row.q75)}</TableCell>
              <TableCell className="text-right">{formatNumber(row.max)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <p className="text-xs text-muted-foreground mt-2 px-2">
        Summary statistics for: {data.metadata.value_column}
      </p>
    </div>
  );
}
