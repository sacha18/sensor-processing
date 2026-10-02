import { useStageData, useSessionStages, useRunSessionStage, useJobStatus, useUpdateQCConfig, useQCConfig } from '../../../api/hooks';
import { useAlertDialog } from '../../../hooks/useAlertDialog';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../components/ui/card';
import { Loader2, Droplets, Activity, Info, AlertTriangle, Save } from 'lucide-react';
import { BeforeAfterChart } from '../../../components/charts/BeforeAfterChart';
import { SensorSelector } from '../../../components/ui/SensorSelector';
import { ParamsUploader } from '../../../components/tms/ParamsUploader';
import { CalibrationRuleForm, type CalibrationRule } from '../../../components/tms/CalibrationRuleForm';
import { CalibrationRulesList } from '../../../components/tms/CalibrationRulesList';
import { Button } from '../../../components/ui/button';
import { useState, useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';

interface CalibrationStepProps {
  sessionId: string;
  pipelineType: string;
}

// Helper functions for calibration rules
function getCalibrationRules(sessionId: string): Array<CalibrationRule & { index: number }> {
  const key = `calibration_rules_${sessionId}`;
  const stored = localStorage.getItem(key);
  if (!stored) return [];
  try {
    const rules = JSON.parse(stored);
    return rules.map((rule: CalibrationRule, index: number) => ({ ...rule, index }));
  } catch {
    return [];
  }
}

function setCalibrationRules(sessionId: string, rules: CalibrationRule[]) {
  const key = `calibration_rules_${sessionId}`;
  localStorage.setItem(key, JSON.stringify(rules));
}

// Calibration params examples
const CALIBRATION_EXAMPLE_CSV = `sensor_id,coef_0,coef_1,coef_2,coef_3,coef_4,coef_5,valid_from,valid_to,notes
*,-11.236,21.421,-18.828,9.3021,-2.7615,0.50315,,,"TOMST universal calibration"
95648949,0,1,0,,,2025-06-01,,"Linear calibration for one sensor"`;

const CALIBRATION_EXAMPLE_JSON = JSON.stringify([
  { sensor_id: "*", coef_0: -11.236, coef_1: 21.421, coef_2: -18.828, coef_3: 9.3021, coef_4: -2.7615, coef_5: 0.50315, valid_from: null, valid_to: null, notes: "TOMST universal calibration" },
  { sensor_id: "95648949", coef_0: 0, coef_1: 1, coef_2: 0, coef_3: null, coef_4: null, coef_5: null, valid_from: "2025-06-01", valid_to: null, notes: "Linear calibration for one sensor" }
], null, 2);

export function CalibrationStep({ sessionId, pipelineType }: CalibrationStepProps) {
  const queryClient = useQueryClient();
  const { showAlert } = useAlertDialog();
  const [runningJobId, setRunningJobId] = useState<string | null>(null);
  const jobTriggeredRef = useRef(false);
  const [isApplyingChanges, setIsApplyingChanges] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  // Calibration rules state
  const [calibrationRules, setCalibrationRulesState] = useState<Array<CalibrationRule & { index: number}>>([]);

  const updateQCConfig = useUpdateQCConfig();
  const { data: qcConfigData } = useQCConfig(sessionId, pipelineType);

  // Load calibration rules on mount
  useEffect(() => {
    setCalibrationRulesState(getCalibrationRules(sessionId));
  }, [sessionId]);

  // Check which stages exist
  const { data: stagesInfo, refetch: refetchStages } = useSessionStages(sessionId, pipelineType);
  const runStage = useRunSessionStage();

  // Poll job status if running
  const { data: jobStatus } = useJobStatus(runningJobId, !!runningJobId);

  // Check if stages exist
  const correctedStageExists = stagesInfo?.stages.some(s => s.base_name === 'corrected');
  const calibratedStageExists = stagesInfo?.stages.some(s => s.base_name === 'calibrated');

  // Load stage data - only when stage exists
  const { data: beforeData, isLoading: beforeLoading, error: beforeError } = useStageData(
    sessionId,
    correctedStageExists ? 'corrected' : null,
    pipelineType,
    1000
  );
  const { data: afterData, isLoading: afterLoading, error: afterError } = useStageData(
    sessionId,
    calibratedStageExists ? 'calibrated' : null,
    pipelineType,
    1000
  );

  // Auto-trigger calibrated job if corrected exists but calibrated doesn't
  useEffect(() => {
    if (stagesInfo && correctedStageExists && !calibratedStageExists && !runningJobId && !jobTriggeredRef.current) {
      console.log('Calibrated stage not found, triggering job...');
      jobTriggeredRef.current = true;
      runStage.mutateAsync({
        sessionId,
        stageName: 'calibrated',
        pipelineType
      }).then(result => {
        console.log('Calibration job started:', result.job_id);
        setRunningJobId(result.job_id);
      }).catch(error => {
        console.error('Failed to start calibration job:', error);
        jobTriggeredRef.current = false;
      });
    }
    // Reset trigger flag when stage exists (job completed successfully)
    if (calibratedStageExists && jobTriggeredRef.current) {
      jobTriggeredRef.current = false;
    }
  }, [stagesInfo, correctedStageExists, calibratedStageExists, runningJobId, sessionId, pipelineType, runStage]);

  // When job completes, refetch stages list and invalidate stage data
  useEffect(() => {
    if (jobStatus?.status === 'finished') {
      console.log('Calibration job completed, refetching stages and invalidating data...');
      setRunningJobId(null);
      jobTriggeredRef.current = false;
      setIsApplyingChanges(false);
      refetchStages();
      // Invalidate stage data to force refetch
      queryClient.invalidateQueries({ queryKey: ['stage-data', sessionId, 'calibrated', pipelineType] });
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

  // Get sensor options for the form
  const sensorOptions = ['*', ...uniqueSensors];

  // Handlers for calibration rules
  const handleUploadRules = async (file: File): Promise<{ success: boolean; message: string; rowsAdded?: number }> => {
    try {
      const text = await file.text();
      let newRules: CalibrationRule[] = [];

      if (file.name.endsWith('.json')) {
        newRules = JSON.parse(text);
      } else if (file.name.endsWith('.csv')) {
        const lines = text.split('\n').filter(l => l.trim());
        const headers = lines[0].split(',').map(h => h.trim());

        for (let i = 1; i < lines.length; i++) {
          const values = lines[i].split(',');
          const rule: any = {};
          headers.forEach((header, idx) => {
            const value = values[idx]?.trim();
            if (value) {
              if (header.startsWith('coef_')) {
                rule[header] = parseFloat(value);
              } else {
                rule[header] = value;
              }
            }
          });
          if (rule.sensor_id) {
            newRules.push(rule as CalibrationRule);
          }
        }
      }

      if (newRules.length === 0) {
        return { success: false, message: 'No valid rules found in file' };
      }

      const allRules = [...calibrationRules.map(r => ({ ...r, index: undefined })), ...newRules];
      setCalibrationRules(sessionId, allRules as CalibrationRule[]);
      setCalibrationRulesState(getCalibrationRules(sessionId));

      return {
        success: true,
        message: `Added ${newRules.length} rule(s) from ${file.name}`,
        rowsAdded: newRules.length
      };
    } catch (error) {
      return { success: false, message: `Failed to parse file: ${String(error)}` };
    }
  };

  const handleAddRule = async (rule: CalibrationRule) => {
    const allRules = [...calibrationRules.map(r => ({ ...r, index: undefined })), rule];
    setCalibrationRules(sessionId, allRules as CalibrationRule[]);
    setCalibrationRulesState(getCalibrationRules(sessionId));
    setHasUnsavedChanges(true);
  };

  const handleDeleteRule = async (index: number) => {
    const allRules = calibrationRules.filter(r => r.index !== index).map(r => ({ ...r, index: undefined }));
    setCalibrationRules(sessionId, allRules as CalibrationRule[]);
    setCalibrationRulesState(getCalibrationRules(sessionId));
    setHasUnsavedChanges(true);
  };

  // Helper to get all params from localStorage
  const getLocalStorageParams = () => {
    const fieldEventsKey = `field_events_${sessionId}`;
    const fieldEventsStored = localStorage.getItem(fieldEventsKey);
    const fieldEvents = fieldEventsStored ? JSON.parse(fieldEventsStored) : [];

    const correctionKey = `correction_rules_${sessionId}`;
    const correctionStored = localStorage.getItem(correctionKey);
    const correctionTable = correctionStored ? JSON.parse(correctionStored) : [];

    const calibrationKey = `calibration_rules_${sessionId}`;
    const calibrationStored = localStorage.getItem(calibrationKey);
    const calibrationTable = calibrationStored ? JSON.parse(calibrationStored) : [];

    // Get QC config from API data (not localStorage)
    const qcCfg = qcConfigData?.qc_cfg || {};

    return { fieldEvents, correctionTable, calibrationTable, qcCfg };
  };

  // Apply changes - save config and re-run calibration stage
  const handleApplyChanges = async () => {
    setIsApplyingChanges(true);
    try {
      const { fieldEvents, correctionTable, calibrationTable, qcCfg } = getLocalStorageParams();

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

      const result = await runStage.mutateAsync({
        sessionId,
        stageName: 'calibrated',
        pipelineType
      });

      setRunningJobId(result.job_id);
      setHasUnsavedChanges(false);
    } catch (error) {
      console.error('Failed to apply calibration changes:', error);
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
        {!jobStatus && <p className="text-sm text-muted-foreground">Loading calibration data...</p>}
      </div>
    );
  }

  // Waiting for corrected stage
  if (!correctedStageExists) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Info className="h-12 w-12 mx-auto mb-4" />
        <p>Please complete the Signal Correction step first</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12 text-destructive">
        Error loading calibration data: {String(error)}
      </div>
    );
  }

  if (!data || !beforeData) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        No calibration data available yet
      </div>
    );
  }

  // Check for VWC column
  const hasVWC = data.columns.some(col => col.toLowerCase().includes('vwc'));
  const vwcColumn = data.columns.find(col => col.toLowerCase().includes('vwc')) || 'vwc';

  // Calculate average VWC if available
  let avgVWC = 0;
  if (hasVWC) {
    const vwcValues = data.data
      .map((row: any) => row[vwcColumn])
      .filter((v: any) => v !== null && v !== undefined && !isNaN(v));
    if (vwcValues.length > 0) {
      avgVWC = vwcValues.reduce((a: number, b: number) => a + b, 0) / vwcValues.length;
    }
  }

  // Prepare before/after data for selected sensor
  const beforeSensorData = beforeData.data.filter((row: any) => row.sensor_id === selectedSensor);
  const afterSensorData = data.data.filter((row: any) => row.sensor_id === selectedSensor);

  return (
    <div className="space-y-6 pb-24">
      <div>
        <h2 className="text-2xl font-bold mb-2">VWC Calibration</h2>
        <p className="text-muted-foreground">
          Volumetric Water Content calculated from corrected signal using polynomial calibration
        </p>
      </div>

      {/* Calibration Parameters Management */}
      <Card>
        <CardHeader>
          <CardTitle>Calibration Parameters</CardTitle>
          <CardDescription>
            Polynomial coefficients for VWC calibration curve (Signal → VWC)
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <ParamsUploader
            title="Upload calibration params CSV/JSON"
            description="Polynomial coefficients (coef_0 through coef_5) for calibrating VWC from corrected Signal. Sensor = '*' applies to every sensor."
            exampleFormat={{
              columns: 'sensor_id (blank or "*" = every sensor), coef_0, coef_1, coef_2, coef_3, coef_4, coef_5, valid_from, valid_to, notes',
              csvExample: CALIBRATION_EXAMPLE_CSV,
              jsonExample: CALIBRATION_EXAMPLE_JSON,
            }}
            onUpload={handleUploadRules}
          />

          <CalibrationRuleForm
            sensorOptions={sensorOptions}
            onSubmit={handleAddRule}
          />

          <div>
            <CalibrationRulesList
              rules={calibrationRules}
              onDelete={handleDeleteRule}
            />
          </div>

          {/* Apply changes button */}
          {hasUnsavedChanges && (
            <div className="flex items-center gap-3 p-4 bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-lg">
              <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 flex-shrink-0" />
              <p className="text-sm text-blue-800 dark:text-blue-200 flex-1">
                You have unsaved calibration rule changes. Click "Apply changes" to recalculate with new parameters.
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
          {data.columns.includes('is_qc_missing_calibration_params') && (
            (() => {
              const missingCount = data.data.filter((row: any) =>
                row.is_qc_missing_calibration_params === true || row.is_qc_missing_calibration_params === 1
              ).length;
              return missingCount > 0 ? (
                <div className="flex items-start gap-2 p-3 bg-orange-50 dark:bg-orange-950 border border-orange-200 dark:border-orange-800 rounded-lg">
                  <AlertTriangle className="h-5 w-5 text-orange-600 dark:text-orange-400 flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-orange-800 dark:text-orange-200">
                    {missingCount} reading(s) have no matching calibration parameters - VWC left as NA.
                  </p>
                </div>
              ) : null;
            })()
          )}
        </CardContent>
      </Card>

      {/* Calibration metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Rows</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{data.total_rows.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">
              calibrated observations
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Sensors</CardTitle>
            <Droplets className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{uniqueSensors.length}</div>
            <p className="text-xs text-muted-foreground">
              with VWC calibration
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Average VWC</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {hasVWC ? avgVWC.toFixed(2) : '-'}
            </div>
            <p className="text-xs text-muted-foreground">
              {hasVWC ? 'm³/m³' : 'Not available'}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Before/After Comparison: Signal → VWC */}
      {uniqueSensors.length > 0 && hasVWC && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>VWC Calibration: Signal to VWC</CardTitle>
                <CardDescription>
                  Transformation from corrected signal values to volumetric water content
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
                  [selectedSensor]: beforeSensorData.map((row: any) => row.signal_corrected || row.signal_raw || 0),
                },
                // No QC flags - Initial QC already applied
              }}
              afterData={{
                timestamp: afterSensorData.map((row: any) => row.timestamp),
                values: {
                  [selectedSensor]: afterSensorData.map((row: any) => {
                    const val = row[vwcColumn];
                    return val !== null && val !== undefined ? Number(val) : 0;
                  }),
                },
                // No QC flags - focus on calibration transformation
              }}
              beforeTitle="Corrected Signal"
              afterTitle="VWC (m³/m³)"
              yAxisLabel="Value"
              height={400}
            />
          </CardContent>
        </Card>
      )}

      {/* Calibration info */}
      <Card>
        <CardHeader>
          <CardTitle>Calibration Method</CardTitle>
          <CardDescription>
            Polynomial equation parameters
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2 text-sm">
            <div className="flex items-center justify-between py-2 border-b">
              <span className="font-medium">Equation Type</span>
              <span className="text-muted-foreground">
                Polynomial (degree varies by sensor)
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b">
              <span className="font-medium">Input</span>
              <span className="text-muted-foreground">
                Corrected signal values
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b">
              <span className="font-medium">Output</span>
              <span className="text-muted-foreground">
                VWC (m³/m³)
              </span>
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="font-medium">Coverage</span>
              <span className="text-muted-foreground">
                {data.total_rows.toLocaleString()} observations calibrated
              </span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
