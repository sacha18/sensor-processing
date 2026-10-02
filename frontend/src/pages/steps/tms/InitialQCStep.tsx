import { useStageData, useSessionStages, useRunSessionStage, useJobStatus, useQCConfig, useUpdateQCConfig } from '../../../api/hooks';
import { useAlertDialog } from '../../../hooks/useAlertDialog';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../components/ui/card';
import { Loader2, AlertTriangle, CheckCircle, Thermometer, Activity, Shield, Info } from 'lucide-react';
import { FacetGridChart } from '../../../components/charts/FacetGridChart';
import { SensorSelector } from '../../../components/ui/SensorSelector';
import { FieldEventsManager } from '../../../components/tms/FieldEventsManager';
import { ParametersSidebar } from '../../../components/tms/ParametersSidebar';
import { useState, useEffect, useRef } from 'react';
import { Label } from '../../../components/ui/label';
import { Switch } from '../../../components/ui/switch';
import { Slider } from '../../../components/ui/slider';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { useQueryClient } from '@tanstack/react-query';

interface InitialQCStepProps {
  sessionId: string;
  pipelineType: string;
  onValidate?: () => void;
  showingComparison: boolean;
  onBackToParams?: () => void;
  isAutomated?: boolean;
  automatedStatus?: string;
}

export function InitialQCStep({ sessionId, pipelineType, onValidate, showingComparison, onBackToParams, isAutomated = false, automatedStatus }: InitialQCStepProps) {
  const queryClient = useQueryClient();
  const { showAlert } = useAlertDialog();
  const [runningJobId, setRunningJobId] = useState<string | null>(null);
  const jobTriggeredRef = useRef(false);
  const [isApplyingChanges, setIsApplyingChanges] = useState(false);

  // QC Configuration state
  const [selectedChannelsToEdit, setSelectedChannelsToEdit] = useState<string[]>(['t1']);
  const { data: qcConfigData } = useQCConfig(sessionId, pipelineType);
  const updateQCConfig = useUpdateQCConfig();

  // Local state for QC parameters (initialized from API)
  const [qcParams, setQcParams] = useState<Record<string, any>>({});
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  // Initialize QC params from API when loaded
  useEffect(() => {
    if (qcConfigData?.qc_cfg) {
      setQcParams(qcConfigData.qc_cfg);
      setHasUnsavedChanges(false);
    }
  }, [qcConfigData]);

  // Check which stages exist
  const { data: stagesInfo, refetch: refetchStages } = useSessionStages(sessionId, pipelineType);
  const runStage = useRunSessionStage();

  // Poll job status if running
  const { data: jobStatus } = useJobStatus(runningJobId, !!runningJobId);

  // Check if stages exist
  const metadataStageExists = stagesInfo?.stages.some(s => s.base_name === 'with_metadata');
  const initialQCStageExists = stagesInfo?.stages.some(s => s.base_name === 'initial_qc');

  // Load BEFORE data (with_metadata) for comparison
  const { data: beforeData } = useStageData(
    sessionId,
    metadataStageExists ? 'with_metadata' : null,
    pipelineType,
    1000
  );

  // Load AFTER data (initial_qc) - current QC results
  const { data, isLoading, error, refetch: refetchQCData } = useStageData(
    sessionId,
    initialQCStageExists ? 'initial_qc' : null,
    pipelineType,
    1000
  );

  // Auto-trigger initial_qc job if with_metadata exists but initial_qc doesn't
  // BUT only for manual sessions, not automated ones
  useEffect(() => {
    if (isAutomated) {
      // Skip auto-triggering for automated sessions - they should already have all stages
      return;
    }

    if (stagesInfo && metadataStageExists && !initialQCStageExists && !runningJobId && !jobTriggeredRef.current) {
      console.log('Initial QC stage not found, triggering job...');
      jobTriggeredRef.current = true;
      runStage.mutateAsync({
        sessionId,
        stageName: 'initial_qc',
        pipelineType
      }).then(result => {
        console.log('Initial QC job started:', result.job_id);
        setRunningJobId(result.job_id);
      }).catch(error => {
        console.error('Failed to start initial QC job:', error);
        jobTriggeredRef.current = false;
      });
    }
    // Reset trigger flag when stage exists (job completed successfully)
    if (initialQCStageExists && jobTriggeredRef.current) {
      jobTriggeredRef.current = false;
    }
  }, [isAutomated, stagesInfo, metadataStageExists, initialQCStageExists, runningJobId, sessionId, pipelineType, runStage]);

  // When job completes, refetch stages list and invalidate stage data
  useEffect(() => {
    if (jobStatus?.status === 'finished') {
      console.log('Initial QC job completed, refetching stages and invalidating data...');
      setRunningJobId(null);
      setIsApplyingChanges(false);
      refetchStages();
      // Invalidate stage data to force refetch
      queryClient.invalidateQueries({ queryKey: ['stage-data', sessionId, 'initial_qc', pipelineType] });
    }
  }, [jobStatus?.status, refetchStages, queryClient, sessionId, pipelineType]);

  // Initialize state before any conditional returns
  const [selectedSensor, setSelectedSensor] = useState<string>('');

  const uniqueSensors = data ? [...new Set(data.data.map((row: any) => row.sensor_id))] : [];

  // Update selected sensor when data loads
  useEffect(() => {
    if (!selectedSensor && uniqueSensors.length > 0) {
      setSelectedSensor(uniqueSensors[0]);
    }
  }, [selectedSensor, uniqueSensors]);

  // Handler for final validation after seeing comparison
  const handleFinalValidate = () => {
    if (onValidate) {
      onValidate();
    }
  };

  // Helper to update QC param for all selected channels
  const updateChannelParam = (param: string, value: any) => {
    setQcParams(prev => {
      const updated = { ...prev };
      selectedChannelsToEdit.forEach(channel => {
        updated[channel] = {
          ...updated[channel],
          [param]: value
        };
      });
      return updated;
    });
    setHasUnsavedChanges(true);
  };

  // Get merged channel params from all selected channels
  // If params differ across channels, show the first channel's value
  const channelParams = selectedChannelsToEdit.length > 0
    ? qcParams[selectedChannelsToEdit[0]] || {}
    : {};

  // Helper to get all params from localStorage
  const getLocalStorageParams = () => {
    // Get field events
    const fieldEventsKey = `field_events_${sessionId}`;
    const fieldEventsStored = localStorage.getItem(fieldEventsKey);
    const fieldEvents = fieldEventsStored ? JSON.parse(fieldEventsStored) : [];

    // Get correction rules
    const correctionKey = `correction_rules_${sessionId}`;
    const correctionStored = localStorage.getItem(correctionKey);
    const correctionTable = correctionStored ? JSON.parse(correctionStored) : [];

    // Get calibration rules
    const calibrationKey = `calibration_rules_${sessionId}`;
    const calibrationStored = localStorage.getItem(calibrationKey);
    const calibrationTable = calibrationStored ? JSON.parse(calibrationStored) : [];

    return { fieldEvents, correctionTable, calibrationTable };
  };

  // Apply QC changes - save config and re-run QC
  const handleApplyChanges = async () => {
    setIsApplyingChanges(true);
    try {
      // Get all params from localStorage
      const { fieldEvents, correctionTable, calibrationTable } = getLocalStorageParams();

      // Save config (all params)
      await updateQCConfig.mutateAsync({
        sessionId,
        config: {
          qc_cfg: qcParams,
          field_events: fieldEvents,
          correction_table: correctionTable,
          calibration_table: calibrationTable
        },
        pipelineType
      });

      // Re-run initial_qc job with new parameters
      const result = await runStage.mutateAsync({
        sessionId,
        stageName: 'initial_qc',
        pipelineType
      });

      setRunningJobId(result.job_id);
      setHasUnsavedChanges(false);
    } catch (error) {
      console.error('Failed to apply QC changes:', error);
      showAlert({
        variant: 'error',
        message: 'Failed to apply changes: ' + String(error),
      });
      setIsApplyingChanges(false);
    }
  };

  // Show loading/job progress (but not when just applying changes - we'll show inline loader)
  if (!stagesInfo || (runningJobId && !isApplyingChanges) || (isLoading && !data)) {
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
        {!jobStatus && <p className="text-sm text-muted-foreground">Loading QC data...</p>}
      </div>
    );
  }

  // Waiting for metadata stage
  if (!metadataStageExists) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Info className="h-12 w-12 mx-auto mb-4" />
        <p>Please complete the Metadata step first</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12 text-destructive">
        Error loading QC data: {String(error)}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        No QC data available yet
      </div>
    );
  }

  // Count QC flags per channel
  const channels = ['t1', 't2', 't3', 'signal'];
  const qcMethods = ['hampel', 'flatline', 'range', 'rate'];

  const flagCountsByChannel: Record<string, number> = {};
  channels.forEach(channel => {
    const channelQcCols = qcMethods.map(method => `is_qc_${method}_${channel}`);
    flagCountsByChannel[channel] = data.data.filter((row: any) =>
      channelQcCols.some(col => row[col] === true || row[col] === 1)
    ).length;
  });

  const totalFlagged = Object.values(flagCountsByChannel).reduce((a, b) => a + b, 0);
  const passedRows = data.sampled_rows - totalFlagged;

  // Prepare data for selected sensor
  const sensorData = data.data.filter((row: any) => row.sensor_id === selectedSensor);

  // Debug: log available columns
  if (sensorData.length > 0) {
    console.log('Available columns:', Object.keys(sensorData[0]));
    console.log('Sample row:', sensorData[0]);
  }

  // Build QC flags by method for each channel
  const buildChannelFlags = (channel: string) => {
    const flags: Record<string, boolean[]> = {};
    qcMethods.forEach(method => {
      const colName = `is_qc_${method}_${channel}`;
      flags[method] = sensorData.map((row: any) => row[colName] === true || row[colName] === 1);
    });

    // Debug logging
    const totalFlags = Object.values(flags).reduce((sum, flagArray) =>
      sum + flagArray.filter(f => f).length, 0
    );
    if (totalFlags > 0) {
      console.log(`Channel ${channel}: ${totalFlags} total flags`, flags);
    }

    return flags;
  };

  return (
    <div className="pb-24">
      <div className="mb-6">
        <h2 className="text-2xl font-bold mb-2">
          {showingComparison ? 'Initial Quality Control - Before/After Comparison' : 'Initial Quality Control'}
        </h2>
        <p className="text-muted-foreground">
          {showingComparison
            ? 'Review the differences between pre-QC and post-QC data'
            : 'Multi-method QC: Hampel filter, flatline detection, range checks, rate-of-change'
          }
        </p>
      </div>

      {/* Two column layout: sticky controls on left, content on right */}
      <div className="flex gap-6">
        {/* Left column: QC Parameters (sticky) - hidden in comparison mode or automated sessions (except when needs attention) */}
        {!showingComparison && (!isAutomated || automatedStatus === 'needs_attention') && (
          <ParametersSidebar
            title="Initial QC Parameters"
            description="Per-channel quality control settings"
            icon={<Shield className="h-5 w-5" />}
            hasUnsavedChanges={hasUnsavedChanges}
            isApplying={isApplyingChanges}
            onApply={handleApplyChanges}
            applyButtonText="Apply & Re-run"
          >
                {/* Multi-Channel Selector for params editing */}
                <div className="space-y-1.5">
                  <Label className="text-xs">Edit Channel Params</Label>
                  <div className="space-y-1.5">
                    {['t1', 't2', 't3', 'signal'].map(channel => (
                      <div key={channel} className="flex items-center space-x-2">
                        <input
                          type="checkbox"
                          id={`edit-${channel}`}
                          checked={selectedChannelsToEdit.includes(channel)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setSelectedChannelsToEdit([...selectedChannelsToEdit, channel]);
                            } else {
                              setSelectedChannelsToEdit(selectedChannelsToEdit.filter(c => c !== channel));
                            }
                          }}
                          disabled={isApplyingChanges}
                          className="h-4 w-4 rounded border-gray-300"
                        />
                        <label htmlFor={`edit-${channel}`} className="text-xs font-medium uppercase cursor-pointer">
                          {channel === 'signal' ? 'Signal' : channel.toUpperCase()}
                        </label>
                      </div>
                    ))}
                  </div>
                  <p className="text-[10px] text-muted-foreground mt-1">
                    Changes apply to all selected channels
                  </p>
                </div>

                {/* Hampel Filter */}
                <div className="space-y-2 border-t pt-3">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs">Hampel (Spikes)</Label>
                    <Switch
                      checked={channelParams.use_hampel ?? true}
                      onCheckedChange={(checked) => updateChannelParam('use_hampel', checked)}
                      disabled={isApplyingChanges}
                    />
                  </div>
                  {channelParams.use_hampel !== false && (
                    <>
                      <div className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span>MAD Threshold</span>
                          <span className="font-mono text-[10px]">{channelParams.hampel_k ?? 3.0}</span>
                        </div>
                        <Slider
                          min={3}
                          max={10}
                          step={0.5}
                          value={[channelParams.hampel_k ?? 3.0]}
                          onValueChange={([val]) => updateChannelParam('hampel_k', val)}
                          disabled={isApplyingChanges}
                        />
                      </div>
                      <div className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span>Window</span>
                          <span className="font-mono text-[10px]">{channelParams.hampel_half_window ?? 5}</span>
                        </div>
                        <Slider
                          min={2}
                          max={10}
                          step={1}
                          value={[channelParams.hampel_half_window ?? 5]}
                          onValueChange={([val]) => updateChannelParam('hampel_half_window', val)}
                          disabled={isApplyingChanges}
                        />
                      </div>
                    </>
                  )}
                </div>

                {/* Flatline Detection */}
                <div className="space-y-2 border-t pt-3">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs">Flatline</Label>
                    <Switch
                      checked={channelParams.use_flatline ?? true}
                      onCheckedChange={(checked) => updateChannelParam('use_flatline', checked)}
                      disabled={isApplyingChanges}
                    />
                  </div>
                  {channelParams.use_flatline !== false && (
                    <div className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span>Min readings</span>
                        <span className="font-mono text-[10px]">{channelParams.flatline_min_run ?? 50}</span>
                      </div>
                      <Slider
                        min={3}
                        max={200}
                        step={1}
                        value={[channelParams.flatline_min_run ?? 50]}
                        onValueChange={([val]) => updateChannelParam('flatline_min_run', val)}
                        disabled={isApplyingChanges}
                      />
                    </div>
                  )}
                </div>

                {/* Range Check (Percentile) */}
                <div className="space-y-2 border-t pt-3">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs">Range</Label>
                    <Switch
                      checked={channelParams.use_percentile ?? false}
                      onCheckedChange={(checked) => updateChannelParam('use_percentile', checked)}
                      disabled={isApplyingChanges}
                    />
                  </div>
                  {channelParams.use_percentile && (
                    <div className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span>Percentile bounds</span>
                        <span className="font-mono text-[10px]">
                          {channelParams.pct_low ?? 0}% - {channelParams.pct_high ?? 100}%
                        </span>
                      </div>
                      <Slider
                        min={0}
                        max={100}
                        step={1}
                        value={[channelParams.pct_low ?? 0, channelParams.pct_high ?? 100]}
                        onValueChange={([low, high]) => {
                          updateChannelParam('pct_low', low);
                          updateChannelParam('pct_high', high);
                        }}
                        disabled={isApplyingChanges}
                      />
                    </div>
                  )}
                </div>

                {/* Rate of Change */}
                <div className="space-y-2 border-t pt-3">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs">Rate</Label>
                    <Switch
                      checked={channelParams.use_rate ?? true}
                      onCheckedChange={(checked) => updateChannelParam('use_rate', checked)}
                      disabled={isApplyingChanges}
                    />
                  </div>
                  {channelParams.use_rate !== false && (
                    <div className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span>Threshold</span>
                        <span className="font-mono text-[10px]">{channelParams.rate_k ?? 10.0}x</span>
                      </div>
                      <Slider
                        min={2}
                        max={20}
                        step={0.5}
                        value={[channelParams.rate_k ?? 10.0]}
                        onValueChange={([val]) => updateChannelParam('rate_k', val)}
                        disabled={isApplyingChanges}
                      />
                    </div>
                  )}
                </div>
          </ParametersSidebar>
        )}

        {/* Right column: QC Results and Charts (scrollable) - full width in comparison mode or automated sessions (except when needs attention) */}
        <div className={(showingComparison || (isAutomated && automatedStatus !== 'needs_attention')) ? "w-full space-y-6" : "flex-1 space-y-6"}>

      {showingComparison && beforeData ? (
        /* BEFORE/AFTER COMPARISON VIEW */
        <>
          {/* Comparison Header with Sensor Selector */}
          <Card className="bg-blue-50 dark:bg-blue-950 border-blue-200">
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-semibold">Before/After Comparison - Review QC Results</div>
                  <div className="text-sm text-muted-foreground">
                    Compare raw data (left) vs QC-flagged data (right)
                  </div>
                </div>
                {uniqueSensors.length > 1 && (
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-medium">Sensor:</span>
                    <SensorSelector
                      sensors={uniqueSensors}
                      selectedSensor={selectedSensor}
                      onSensorChange={setSelectedSensor}
                    />
                    <span className="text-xs text-muted-foreground">
                      ({uniqueSensors.indexOf(selectedSensor) + 1} of {uniqueSensors.length})
                    </span>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Side-by-side charts */}
          <div className="grid grid-cols-2 gap-6">
            {/* BEFORE (left) - Raw data without QC flags */}
            <Card>
              <CardHeader>
                <CardTitle>Before QC</CardTitle>
                <CardDescription>Raw sensor data (T1, T2, T3, Signal)</CardDescription>
              </CardHeader>
              <CardContent>
                {(() => {
                  const beforeSensorData = beforeData.data.filter((row: any) => row.sensor_id === selectedSensor);
                  return (
                    <FacetGridChart
                      channels={[
                        {
                          name: 't1',
                          label: 'T1',
                          data: {
                            timestamp: beforeSensorData.map((row: any) => row.timestamp),
                            values: { [selectedSensor]: beforeSensorData.map((row: any) => row.t1_raw || 0) },
                          },
                        },
                        {
                          name: 't2',
                          label: 'T2',
                          data: {
                            timestamp: beforeSensorData.map((row: any) => row.timestamp),
                            values: { [selectedSensor]: beforeSensorData.map((row: any) => row.t2_raw || 0) },
                          },
                        },
                        {
                          name: 't3',
                          label: 'T3',
                          data: {
                            timestamp: beforeSensorData.map((row: any) => row.timestamp),
                            values: { [selectedSensor]: beforeSensorData.map((row: any) => row.t3_raw || 0) },
                          },
                        },
                        {
                          name: 'signal',
                          label: 'Signal',
                          data: {
                            timestamp: beforeSensorData.map((row: any) => row.timestamp),
                            values: { [selectedSensor]: beforeSensorData.map((row: any) => row.signal_raw || 0) },
                          },
                        },
                      ]}
                      height={800}
                      showLegend={false}
                    />
                  );
                })()}
              </CardContent>
            </Card>

            {/* AFTER (right) - With QC flags */}
            <Card>
              <CardHeader>
                <CardTitle>After QC</CardTitle>
                <CardDescription>With quality flags (colored by method)</CardDescription>
              </CardHeader>
              <CardContent>
                <FacetGridChart
                  channels={[
                    {
                      name: 't1',
                      label: 'T1',
                      data: {
                        timestamp: sensorData.map((row: any) => row.timestamp),
                        values: { [selectedSensor]: sensorData.map((row: any) => row.t1_raw || 0) },
                        flags: buildChannelFlags('t1'),
                      },
                    },
                    {
                      name: 't2',
                      label: 'T2',
                      data: {
                        timestamp: sensorData.map((row: any) => row.timestamp),
                        values: { [selectedSensor]: sensorData.map((row: any) => row.t2_raw || 0) },
                        flags: buildChannelFlags('t2'),
                      },
                    },
                    {
                      name: 't3',
                      label: 'T3',
                      data: {
                        timestamp: sensorData.map((row: any) => row.timestamp),
                        values: { [selectedSensor]: sensorData.map((row: any) => row.t3_raw || 0) },
                        flags: buildChannelFlags('t3'),
                      },
                    },
                    {
                      name: 'signal',
                      label: 'Signal (raw)',
                      data: {
                        timestamp: sensorData.map((row: any) => row.timestamp),
                        values: { [selectedSensor]: sensorData.map((row: any) => row.signal_raw || 0) },
                        flags: buildChannelFlags('signal'),
                      },
                    },
                  ]}
                  height={800}
                  showLegend={true}
                />
              </CardContent>
            </Card>
          </div>

          {/* Validation Actions */}
        </>
      ) : (
        /* NORMAL QC RESULTS VIEW */
        <>
      {/* Overall QC Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">QC Passed</CardTitle>
            <CheckCircle className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{passedRows.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">
              {((passedRows / data.sampled_rows) * 100).toFixed(1)}% of sampled data
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">QC Flagged</CardTitle>
            <AlertTriangle className="h-4 w-4 text-orange-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalFlagged.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">
              {((totalFlagged / data.sampled_rows) * 100).toFixed(1)}% flagged for review
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Rows</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{data.total_rows.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">
              in full dataset
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Per-Channel Flag Counts */}
      <Card>
        <CardHeader>
          <CardTitle>QC Flags by Channel</CardTitle>
          <CardDescription>
            Number of flagged observations in sampled data
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {channels.map(channel => {
              const count = flagCountsByChannel[channel] || 0;
              const percentage = ((count / data.sampled_rows) * 100).toFixed(1);
              return (
                <div key={channel} className="flex items-center gap-3 p-3 border rounded-lg">
                  {channel === 'signal' ? (
                    <Activity className="h-5 w-5 text-blue-500" />
                  ) : (
                    <Thermometer className="h-5 w-5 text-orange-500" />
                  )}
                  <div>
                    <div className="text-sm font-medium uppercase">{channel}</div>
                    <div className="text-lg font-bold">{count}</div>
                    <div className="text-xs text-muted-foreground">{percentage}%</div>
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Sensor Selector & Multi-channel View */}
      {uniqueSensors.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Multi-Channel QC View</CardTitle>
              </div>
              {uniqueSensors.length > 1 && (
                <SensorSelector
                  sensors={uniqueSensors}
                  selectedSensor={selectedSensor}
                  onSensorChange={setSelectedSensor}
                />
              )}
            </div>
          </CardHeader>
          <CardContent className="relative">
            {/* Loading overlay when applying changes */}
            {isApplyingChanges && (
              <div className="absolute inset-0 bg-background/80 backdrop-blur-sm z-10 flex items-center justify-center">
                <div className="flex flex-col items-center gap-3">
                  <Loader2 className="h-8 w-8 animate-spin text-primary" />
                  <p className="text-sm font-medium">Applying QC parameters...</p>
                  {jobStatus && (
                    <p className="text-xs text-muted-foreground">{jobStatus.current_stage}</p>
                  )}
                </div>
              </div>
            )}
            <FacetGridChart
              channels={[
                {
                  name: 't1',
                  label: 'T1',
                  data: {
                    timestamp: sensorData.map((row: any) => row.timestamp),
                    values: { [selectedSensor]: sensorData.map((row: any) => row.t1_raw || 0) },
                    flags: buildChannelFlags('t1'),
                  },
                },
                {
                  name: 't2',
                  label: 'T2',
                  data: {
                    timestamp: sensorData.map((row: any) => row.timestamp),
                    values: { [selectedSensor]: sensorData.map((row: any) => row.t2_raw || 0) },
                    flags: buildChannelFlags('t2'),
                  },
                },
                {
                  name: 't3',
                  label: 'T3',
                  data: {
                    timestamp: sensorData.map((row: any) => row.timestamp),
                    values: { [selectedSensor]: sensorData.map((row: any) => row.t3_raw || 0) },
                    flags: buildChannelFlags('t3'),
                  },
                },
                {
                  name: 'signal',
                  label: 'Signal (raw)',
                  data: {
                    timestamp: sensorData.map((row: any) => row.timestamp),
                    values: { [selectedSensor]: sensorData.map((row: any) => row.signal_raw || 0) },
                    flags: buildChannelFlags('signal'),
                  },
                },
              ]}
              height={800}
              showLegend={true}
            />
          </CardContent>
        </Card>
      )}

      {/* QC Methods Legend */}
      <Card>
        <CardHeader>
          <CardTitle>QC Methods</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded-full" style={{ backgroundColor: '#ee6666' }}></div>
              <div>
                <div className="text-sm font-medium">Hampel Filter</div>
                <div className="text-xs text-muted-foreground">Outliers based on median absolute deviation</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded-full" style={{ backgroundColor: '#fac858' }}></div>
              <div>
                <div className="text-sm font-medium">Flatline Detection</div>
                <div className="text-xs text-muted-foreground">Consecutive identical values</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded-full" style={{ backgroundColor: '#fc8452' }}></div>
              <div>
                <div className="text-sm font-medium">Range Check</div>
                <div className="text-xs text-muted-foreground">Values outside physically plausible bounds</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 rounded-full" style={{ backgroundColor: '#9a60b4' }}></div>
              <div>
                <div className="text-sm font-medium">Rate of Change</div>
                <div className="text-xs text-muted-foreground">Unrealistic jumps between readings</div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

        </>
      )}

      {/* Field Events Section - always rendered to maintain hook order, hidden in comparison mode or automated sessions (except when needs attention) */}
      <div style={{ display: (showingComparison || (isAutomated && automatedStatus !== 'needs_attention')) ? 'none' : 'block' }}>
        <FieldEventsManager
          sessionId={sessionId}
          sensorOptions={['*', ...uniqueSensors]}
          data={data.data}
        />
      </div>
        </div>
        {/* End of right column */}
      </div>
      {/* End of two-column layout */}
    </div>
  );
}
