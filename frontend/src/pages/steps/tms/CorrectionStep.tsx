import { useStageData, useSessionStages, useRunSessionStage, useJobStatus, useUpdateQCConfig, useQCConfig } from '../../../api/hooks';
import { useAlertDialog } from '../../../hooks/useAlertDialog';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../components/ui/card';
import { Loader2, Zap, TrendingUp, Info, AlertTriangle, Save } from 'lucide-react';
import { BeforeAfterChart } from '../../../components/charts/BeforeAfterChart';
import { SensorSelector } from '../../../components/ui/SensorSelector';
import { ParamsUploader } from '../../../components/tms/ParamsUploader';
import { CorrectionRuleForm, type CorrectionRule } from '../../../components/tms/CorrectionRuleForm';
import { CorrectionRulesList } from '../../../components/tms/CorrectionRulesList';
import { Button } from '../../../components/ui/button';
import { useState, useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';

interface CorrectionStepProps {
  sessionId: string;
  pipelineType: string;
}

// Helper to get correction rules from localStorage
function getCorrectionRules(sessionId: string): Array<CorrectionRule & { index: number }> {
  const key = `correction_rules_${sessionId}`;
  const stored = localStorage.getItem(key);
  if (!stored) return [];
  try {
    const rules = JSON.parse(stored);
    return rules.map((rule: CorrectionRule, index: number) => ({ ...rule, index }));
  } catch {
    return [];
  }
}

// Helper to set correction rules in localStorage
function setCorrectionRules(sessionId: string, rules: CorrectionRule[]) {
  const key = `correction_rules_${sessionId}`;
  localStorage.setItem(key, JSON.stringify(rules));
}

// Correction params CSV/JSON examples
const CORRECTION_EXAMPLE_CSV = `sensor_id,correction_type,factor_a,factor_b,valid_from,valid_to,notes
*,one_factor,1.0,,,,"identity (no-op), applies to every sensor"
95648949,two_factor,0.0125,-0.15,2025-06-01,,"two-factor override for one sensor"`;

const CORRECTION_EXAMPLE_JSON = JSON.stringify([
  { sensor_id: "*", correction_type: "one_factor", factor_a: 1.0, factor_b: null, valid_from: null, valid_to: null, notes: "identity (no-op), applies to every sensor" },
  { sensor_id: "95648949", correction_type: "two_factor", factor_a: 0.0125, factor_b: -0.15, valid_from: "2025-06-01", valid_to: null, notes: "two-factor override for one sensor" }
], null, 2);

export function CorrectionStep({ sessionId, pipelineType }: CorrectionStepProps) {
  const queryClient = useQueryClient();
  const { showAlert } = useAlertDialog();
  const [runningJobId, setRunningJobId] = useState<string | null>(null);
  const jobTriggeredRef = useRef(false);
  const [isApplyingChanges, setIsApplyingChanges] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  // Correction rules state
  const [correctionRules, setCorrectionRulesState] = useState<Array<CorrectionRule & { index: number }>>([]);

  const updateQCConfig = useUpdateQCConfig();
  const { data: qcConfigData } = useQCConfig(sessionId, pipelineType);

  // Load correction rules on mount
  useEffect(() => {
    setCorrectionRulesState(getCorrectionRules(sessionId));
  }, [sessionId]);

  // Check which stages exist
  const { data: stagesInfo, refetch: refetchStages } = useSessionStages(sessionId, pipelineType);
  const runStage = useRunSessionStage();

  // Poll job status if running
  const { data: jobStatus } = useJobStatus(runningJobId, !!runningJobId);

  // Check if stages exist
  const initialQCStageExists = stagesInfo?.stages.some(s => s.base_name === 'initial_qc');
  const correctedStageExists = stagesInfo?.stages.some(s => s.base_name === 'corrected');

  // Load stage data - only when stage exists
  const { data: beforeData, isLoading: beforeLoading, error: beforeError } = useStageData(
    sessionId,
    initialQCStageExists ? 'initial_qc' : null,
    pipelineType,
    1000
  );
  const { data: afterData, isLoading: afterLoading, error: afterError } = useStageData(
    sessionId,
    correctedStageExists ? 'corrected' : null,
    pipelineType,
    1000
  );

  // Auto-trigger corrected job if initial_qc exists but corrected doesn't
  useEffect(() => {
    if (stagesInfo && initialQCStageExists && !correctedStageExists && !runningJobId && !jobTriggeredRef.current) {
      console.log('Corrected stage not found, triggering job...');
      jobTriggeredRef.current = true;
      runStage.mutateAsync({
        sessionId,
        stageName: 'corrected',
        pipelineType
      }).then(result => {
        console.log('Correction job started:', result.job_id);
        setRunningJobId(result.job_id);
      }).catch(error => {
        console.error('Failed to start correction job:', error);
        jobTriggeredRef.current = false;
      });
    }
    // Reset trigger flag when stage exists (job completed successfully)
    if (correctedStageExists && jobTriggeredRef.current) {
      jobTriggeredRef.current = false;
    }
  }, [stagesInfo, initialQCStageExists, correctedStageExists, runningJobId, sessionId, pipelineType, runStage]);

  // When job completes, refetch stages list and invalidate stage data
  useEffect(() => {
    if (jobStatus?.status === 'finished') {
      console.log('Correction job completed, refetching stages and invalidating data...');
      setRunningJobId(null);
      jobTriggeredRef.current = false;
      setIsApplyingChanges(false);
      refetchStages();
      // Invalidate stage data to force refetch
      queryClient.invalidateQueries({ queryKey: ['stage-data', sessionId, 'corrected', pipelineType] });
    }
  }, [jobStatus?.status, refetchStages, queryClient, sessionId, pipelineType]);

  // Initialize state before any conditional returns
  const uniqueSensors = afterData ? [...new Set(afterData.data.map((row: any) => row.sensor_id))] : [];
  const [selectedSensor, setSelectedSensor] = useState<string>('');

  const isLoading = beforeLoading || afterLoading;
  const error = beforeError || afterError;
  const data = afterData;

  // Update selected sensor when data loads
  if (!selectedSensor && uniqueSensors.length > 0) {
    setSelectedSensor(uniqueSensors[0]);
  }

  // Get sensor options for the form (unique sensors + groups + "*")
  const sensorOptions = ['*', ...uniqueSensors];

  // Handlers for correction rules
  const handleUploadRules = async (file: File): Promise<{ success: boolean; message: string; rowsAdded?: number }> => {
    try {
      const text = await file.text();
      let newRules: CorrectionRule[] = [];

      if (file.name.endsWith('.json')) {
        newRules = JSON.parse(text);
      } else if (file.name.endsWith('.csv')) {
        // Simple CSV parser
        const lines = text.split('\n').filter(l => l.trim());
        const headers = lines[0].split(',').map(h => h.trim());

        for (let i = 1; i < lines.length; i++) {
          const values = lines[i].split(',');
          const rule: any = {};
          headers.forEach((header, idx) => {
            const value = values[idx]?.trim();
            if (value) {
              if (header === 'factor_a' || header === 'factor_b') {
                rule[header] = parseFloat(value);
              } else {
                rule[header] = value;
              }
            }
          });
          if (rule.sensor_id && rule.correction_type && rule.factor_a) {
            newRules.push(rule as CorrectionRule);
          }
        }
      }

      if (newRules.length === 0) {
        return { success: false, message: 'No valid rules found in file' };
      }

      const allRules = [...correctionRules.map(r => ({ ...r, index: undefined })), ...newRules];
      setCorrectionRules(sessionId, allRules as CorrectionRule[]);
      setCorrectionRulesState(getCorrectionRules(sessionId));

      return {
        success: true,
        message: `Added ${newRules.length} rule(s) from ${file.name}`,
        rowsAdded: newRules.length
      };
    } catch (error) {
      return { success: false, message: `Failed to parse file: ${String(error)}` };
    }
  };

  const handleAddRule = async (rule: CorrectionRule) => {
    console.log('Adding correction rule:', rule);
    console.log('Session ID:', sessionId);
    const allRules = [...correctionRules.map(r => ({ ...r, index: undefined })), rule];
    console.log('All rules after adding:', allRules);
    setCorrectionRules(sessionId, allRules as CorrectionRule[]);
    const updated = getCorrectionRules(sessionId);
    console.log('Rules from localStorage after save:', updated);
    setCorrectionRulesState(updated);
    setHasUnsavedChanges(true);
  };

  const handleDeleteRule = async (index: number) => {
    const allRules = correctionRules.filter(r => r.index !== index).map(r => ({ ...r, index: undefined }));
    setCorrectionRules(sessionId, allRules as CorrectionRule[]);
    setCorrectionRulesState(getCorrectionRules(sessionId));
    setHasUnsavedChanges(true);
  };

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

    // Get QC config from API data (not localStorage)
    const qcCfg = qcConfigData?.qc_cfg || {};

    return { fieldEvents, correctionTable, calibrationTable, qcCfg };
  };

  // Apply changes - save config and re-run correction stage
  const handleApplyChanges = async () => {
    setIsApplyingChanges(true);
    try {
      // Get all params from localStorage
      const { fieldEvents, correctionTable, calibrationTable, qcCfg } = getLocalStorageParams();

      // Save config (all params)
      await updateQCConfig.mutateAsync({
        sessionId,
        config: {
          qc_cfg: qcCfg,
          field_events: fieldEvents,
          correction_table: correctionTable,
          calibration_table: calibrationTable
        },
        pipelineType
      });

      // Re-run corrected job with new parameters
      const result = await runStage.mutateAsync({
        sessionId,
        stageName: 'corrected',
        pipelineType
      });

      setRunningJobId(result.job_id);
      setHasUnsavedChanges(false);
    } catch (error) {
      console.error('Failed to apply correction changes:', error);
      showAlert({
        variant: 'error',
        message: 'Failed to apply changes: ' + String(error),
      });
      setIsApplyingChanges(false);
    }
  };

  // Show loading/job progress
  if (!stagesInfo || runningJobId || isLoading) {
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
        {!jobStatus && <p className="text-sm text-muted-foreground">Loading correction data...</p>}
      </div>
    );
  }

  // Waiting for initial_qc stage
  if (!initialQCStageExists) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Info className="h-12 w-12 mx-auto mb-4" />
        <p>Please complete the Initial QC step first</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12 text-destructive">
        Error loading correction data: {String(error)}
      </div>
    );
  }

  if (!data || !beforeData) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        No correction data available yet
      </div>
    );
  }

  // Check for correction columns
  const hasCorrectionId = data.columns.includes('correction_id');
  const hasSignalCorrected = data.columns.includes('signal_corrected');

  // Prepare before/after data for selected sensor
  const beforeSensorData = beforeData.data.filter((row: any) => row.sensor_id === selectedSensor);
  const afterSensorData = data.data.filter((row: any) => row.sensor_id === selectedSensor);

  return (
    <div className="space-y-6 pb-24">
      <div>
        <h2 className="text-2xl font-bold mb-2">Signal Correction</h2>
        <p className="text-muted-foreground">
          Sensor-specific corrections applied to raw signal values
        </p>
      </div>

      {/* Correction Parameters Management */}
      <Card>
        <CardHeader>
          <CardTitle>Correction Parameters</CardTitle>
          <CardDescription>
            Sensor-specific signal correction rules (one-factor or two-factor)
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <ParamsUploader
            title="Upload correction params CSV/JSON"
            description="Supplied by your team, per sensor or sensor group - not derived by this app. One-factor: a × Signal. Two-factor: a × Signal + b. Sensor = '*' applies to every sensor."
            exampleFormat={{
              columns: 'sensor_id (blank or "*" = every sensor), correction_type (one_factor/two_factor), factor_a, factor_b (two-factor only), valid_from, valid_to, notes',
              csvExample: CORRECTION_EXAMPLE_CSV,
              jsonExample: CORRECTION_EXAMPLE_JSON,
            }}
            onUpload={handleUploadRules}
          />

          <CorrectionRuleForm
            sensorOptions={sensorOptions}
            onSubmit={handleAddRule}
          />

          <div>
            <CorrectionRulesList
              rules={correctionRules}
              onDelete={handleDeleteRule}
            />
          </div>

          {/* Apply changes button - always show if rules exist */}
          {correctionRules.length > 0 && (
            <div className="flex items-center gap-3 p-4 bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-lg">
              <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 flex-shrink-0" />
              <p className="text-sm text-blue-800 dark:text-blue-200 flex-1">
                {hasUnsavedChanges
                  ? 'You have unsaved correction rule changes. Click "Apply changes" to recalculate with new parameters.'
                  : 'Click "Apply changes" to apply correction rules and recalculate the corrected stage.'}
              </p>
              <Button
                onClick={handleApplyChanges}
                disabled={isApplyingChanges}
                className="flex-shrink-0"
              >
                <Save className="h-4 w-4 mr-2" />
                {isApplyingChanges ? 'Applying...' : 'Apply changes'}
              </Button>
            </div>
          )}

          {/* Warning for missing params */}
          {data.columns.includes('is_qc_missing_correction_params') && (
            (() => {
              const missingCount = data.data.filter((row: any) =>
                row.is_qc_missing_correction_params === true || row.is_qc_missing_correction_params === 1
              ).length;
              return missingCount > 0 ? (
                <div className="flex items-start gap-2 p-3 bg-orange-50 dark:bg-orange-950 border border-orange-200 dark:border-orange-800 rounded-lg">
                  <AlertTriangle className="h-5 w-5 text-orange-600 dark:text-orange-400 flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-orange-800 dark:text-orange-200">
                    {missingCount} reading(s) have no matching correction parameters - left uncorrected (NA).
                  </p>
                </div>
              ) : null;
            })()
          )}
        </CardContent>
      </Card>

      {/* Before/After Comparison */}
      {uniqueSensors.length > 0 && hasSignalCorrected && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Signal Correction: Before vs After</CardTitle>
                <CardDescription>
                  Raw signal values before and after applying sensor-specific corrections
                </CardDescription>
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
          <CardContent>
            <BeforeAfterChart
              beforeData={{
                timestamp: beforeSensorData.map((row: any) => row.timestamp),
                values: {
                  [selectedSensor]: beforeSensorData.map((row: any) => row.signal_raw || 0),
                },
                // No QC flags - Initial QC already applied
              }}
              afterData={{
                timestamp: afterSensorData.map((row: any) => row.timestamp),
                values: {
                  [selectedSensor]: afterSensorData.map((row: any) => row.signal_corrected || row.signal_raw || 0),
                },
                // No QC flags - focus on correction effect only
              }}
              beforeTitle="Before Correction (Raw Signal)"
              afterTitle="After Correction (Corrected Signal)"
              yAxisLabel="Signal Value"
              height={400}
            />
          </CardContent>
        </Card>
      )}

    </div>
  );
}
