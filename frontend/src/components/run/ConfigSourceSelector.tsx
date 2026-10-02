import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Label } from '../ui/label';
import { RadioGroup, RadioGroupItem } from '../ui/radio-group';
import { Input } from '../ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Badge } from '../ui/badge';
import { Checkbox } from '../ui/checkbox';
import { FileUp, Database } from 'lucide-react';
import { useDatasets } from '../../api/hooks';
import { ColumnMappingDialog } from './ColumnMappingDialog';
import type { ConfigSource, ColumnMapping } from './types';

interface ConfigSourceSelectorProps {
  pipelineType: string;
  value: ConfigSource;
  onChange: (config: ConfigSource) => void;
}

export function ConfigSourceSelector({
  pipelineType,
  value,
  onChange
}: ConfigSourceSelectorProps) {
  const [sourceType, setSourceType] = useState<'dataset' | 'upload'>(value.type);

  // Fetch published datasets for selection
  const { data: datasetsResponse } = useDatasets({
    pipeline_type: pipelineType,
    status: 'active',
    limit: 100
  });

  const handleSourceTypeChange = (type: 'dataset' | 'upload') => {
    setSourceType(type);
    onChange({
      type,
      ...(type === 'dataset' ? { datasetId: undefined } : {})
    });
  };

  const handleDatasetSelect = (datasetId: string) => {
    onChange({
      type: 'dataset',
      datasetId,
      // By default, use all config from dataset
      useDatasetMetadata: true,
      useDatasetQcParams: true,
      useDatasetCorrections: true,
      useDatasetCalibrations: true,
    });
  };

  const handleDatasetConfigToggle = (configType: 'metadata' | 'qcParams' | 'corrections' | 'calibrations', checked: boolean) => {
    const updates: Partial<ConfigSource> = {};

    if (configType === 'metadata') updates.useDatasetMetadata = checked;
    if (configType === 'qcParams') updates.useDatasetQcParams = checked;
    if (configType === 'corrections') updates.useDatasetCorrections = checked;
    if (configType === 'calibrations') updates.useDatasetCalibrations = checked;

    onChange({
      ...value,
      ...updates
    });
  };

  const handleFileChange = (fileType: 'metadata' | 'qcParams' | 'corrections' | 'calibrations', file: File | null) => {
    const updates: Partial<ConfigSource> = {};

    if (fileType === 'metadata') {
      updates.metadataFile = file || undefined;
      // Clear mapping when file changes
      if (!file) updates.metadataMapping = undefined;
    }
    if (fileType === 'qcParams') updates.qcParamsFile = file || undefined;
    if (fileType === 'corrections') {
      updates.correctionsFile = file || undefined;
      if (!file) updates.correctionsMapping = undefined;
    }
    if (fileType === 'calibrations') {
      updates.calibrationsFile = file || undefined;
      if (!file) updates.calibrationsMapping = undefined;
    }

    onChange({
      ...value,
      ...updates
    });
  };

  const handleMappingChange = (fileType: 'metadata' | 'corrections' | 'calibrations', mapping: ColumnMapping) => {
    const updates: Partial<ConfigSource> = {};

    if (fileType === 'metadata') updates.metadataMapping = mapping;
    if (fileType === 'corrections') updates.correctionsMapping = mapping;
    if (fileType === 'calibrations') updates.calibrationsMapping = mapping;

    onChange({
      ...value,
      ...updates
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Configuration Source</CardTitle>
        <CardDescription>
          Choose how to configure your pipeline parameters
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Source Type Selection */}
        <RadioGroup value={sourceType} onValueChange={handleSourceTypeChange}>
          <div className="flex items-center space-x-2">
            <RadioGroupItem value="dataset" id="dataset" />
            <Label htmlFor="dataset" className="flex items-center gap-2 cursor-pointer">
              <Database className="h-4 w-4" />
              Use configuration from published dataset
            </Label>
          </div>
          <div className="flex items-center space-x-2">
            <RadioGroupItem value="upload" id="upload" />
            <Label htmlFor="upload" className="flex items-center gap-2 cursor-pointer">
              <FileUp className="h-4 w-4" />
              Upload configuration files
            </Label>
          </div>
        </RadioGroup>

        {/* Dataset Selection */}
        {sourceType === 'dataset' && (
          <div className="space-y-4">
            <div className="space-y-3">
              <Label>Select Published Dataset</Label>
              <Select value={value.datasetId} onValueChange={handleDatasetSelect}>
                <SelectTrigger>
                  <SelectValue placeholder="Choose a dataset to copy configuration from" />
                </SelectTrigger>
                <SelectContent>
                  {datasetsResponse?.datasets.map((dataset) => (
                    <SelectItem key={dataset.dataset_id} value={dataset.dataset_id}>
                      <div className="flex items-center justify-between w-full gap-4">
                        <span className="font-medium">{dataset.title}</span>
                        <div className="flex gap-1">
                          {dataset.tags?.map((tag) => (
                            <Badge key={tag} variant="outline" className="text-xs">
                              {tag}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Configuration Import Options */}
            {value.datasetId && (
              <div className="space-y-4 border-t pt-4">
                <div className="text-sm font-medium">Select Configuration to Import</div>
                <div className="text-xs text-muted-foreground mb-3">
                  Check items to import from dataset. Unchecked items can be uploaded manually below.
                </div>

                {/* Metadata Checkbox */}
                <div className="flex items-start space-x-3">
                  <Checkbox
                    id="use-dataset-metadata"
                    checked={value.useDatasetMetadata ?? true}
                    onCheckedChange={(checked) => handleDatasetConfigToggle('metadata', checked as boolean)}
                  />
                  <div className="flex-1">
                    <Label htmlFor="use-dataset-metadata" className="cursor-pointer font-medium">
                      Metadata
                    </Label>
                    <div className="text-xs text-muted-foreground">
                      Sensor deployments, site info, install dates
                    </div>
                  </div>
                </div>

                {/* QC Parameters Checkbox */}
                <div className="flex items-start space-x-3">
                  <Checkbox
                    id="use-dataset-qc"
                    checked={value.useDatasetQcParams ?? true}
                    onCheckedChange={(checked) => handleDatasetConfigToggle('qcParams', checked as boolean)}
                  />
                  <div className="flex-1">
                    <Label htmlFor="use-dataset-qc" className="cursor-pointer font-medium">
                      QC Parameters
                    </Label>
                    <div className="text-xs text-muted-foreground">
                      Hampel, flatline, range, rate detection thresholds
                    </div>
                  </div>
                </div>

                {/* Corrections Checkbox */}
                <div className="flex items-start space-x-3">
                  <Checkbox
                    id="use-dataset-corrections"
                    checked={value.useDatasetCorrections ?? true}
                    onCheckedChange={(checked) => handleDatasetConfigToggle('corrections', checked as boolean)}
                  />
                  <div className="flex-1">
                    <Label htmlFor="use-dataset-corrections" className="cursor-pointer font-medium">
                      Correction Rules
                    </Label>
                    <div className="text-xs text-muted-foreground">
                      Signal correction factors and formulas
                    </div>
                  </div>
                </div>

                {/* Calibrations Checkbox */}
                <div className="flex items-start space-x-3">
                  <Checkbox
                    id="use-dataset-calibrations"
                    checked={value.useDatasetCalibrations ?? true}
                    onCheckedChange={(checked) => handleDatasetConfigToggle('calibrations', checked as boolean)}
                  />
                  <div className="flex-1">
                    <Label htmlFor="use-dataset-calibrations" className="cursor-pointer font-medium">
                      Calibration Rules
                    </Label>
                    <div className="text-xs text-muted-foreground">
                      VWC calibration polynomial coefficients
                    </div>
                  </div>
                </div>

                {/* Manual File Uploads for Unchecked Items */}
                <div className="border-t pt-4 space-y-4">
                  <div className="text-sm font-medium">Manual Uploads (for unchecked items)</div>

                  {/* Metadata File Upload (if not using dataset metadata) */}
                  {!value.useDatasetMetadata && (
                    <div className="space-y-2">
                      <Label htmlFor="metadata-file-hybrid">
                        Metadata (CSV/JSON/XLSX)
                        <span className="text-xs text-muted-foreground ml-2">Required</span>
                      </Label>
                      <Input
                        id="metadata-file-hybrid"
                        type="file"
                        accept=".csv,.json,.xlsx"
                        onChange={(e) => handleFileChange('metadata', e.target.files?.[0] || null)}
                      />
                      {value.metadataFile && (
                        <>
                          <div className="text-xs text-muted-foreground">
                            Selected: {value.metadataFile.name} ({(value.metadataFile.size / 1024).toFixed(2)} KB)
                          </div>
                          <ColumnMappingDialog
                            fileType="metadata"
                            file={value.metadataFile}
                            onMappingChange={(mapping) => handleMappingChange('metadata', mapping)}
                          />
                        </>
                      )}
                    </div>
                  )}

                  {/* QC Params File Upload */}
                  {!value.useDatasetQcParams && (
                    <div className="space-y-2">
                      <Label htmlFor="qc-params-file-hybrid">
                        QC Parameters (JSON)
                        <span className="text-xs text-muted-foreground ml-2">Optional</span>
                      </Label>
                      <Input
                        id="qc-params-file-hybrid"
                        type="file"
                        accept=".json"
                        onChange={(e) => handleFileChange('qcParams', e.target.files?.[0] || null)}
                      />
                      {value.qcParamsFile && (
                        <div className="text-xs text-muted-foreground">
                          Selected: {value.qcParamsFile.name} ({(value.qcParamsFile.size / 1024).toFixed(2)} KB)
                        </div>
                      )}
                    </div>
                  )}

                  {/* Corrections File Upload */}
                  {!value.useDatasetCorrections && (
                    <div className="space-y-2">
                      <Label htmlFor="corrections-file-hybrid">
                        Correction Rules (CSV)
                        <span className="text-xs text-muted-foreground ml-2">Optional</span>
                      </Label>
                      <Input
                        id="corrections-file-hybrid"
                        type="file"
                        accept=".csv"
                        onChange={(e) => handleFileChange('corrections', e.target.files?.[0] || null)}
                      />
                      {value.correctionsFile && (
                        <>
                          <div className="text-xs text-muted-foreground">
                            Selected: {value.correctionsFile.name} ({(value.correctionsFile.size / 1024).toFixed(2)} KB)
                          </div>
                          <ColumnMappingDialog
                            fileType="corrections"
                            file={value.correctionsFile}
                            onMappingChange={(mapping) => handleMappingChange('corrections', mapping)}
                          />
                        </>
                      )}
                    </div>
                  )}

                  {/* Calibrations File Upload */}
                  {!value.useDatasetCalibrations && (
                    <div className="space-y-2">
                      <Label htmlFor="calibrations-file-hybrid">
                        Calibration Rules (CSV)
                        <span className="text-xs text-muted-foreground ml-2">Optional</span>
                      </Label>
                      <Input
                        id="calibrations-file-hybrid"
                        type="file"
                        accept=".csv"
                        onChange={(e) => handleFileChange('calibrations', e.target.files?.[0] || null)}
                      />
                      {value.calibrationsFile && (
                        <>
                          <div className="text-xs text-muted-foreground">
                            Selected: {value.calibrationsFile.name} ({(value.calibrationsFile.size / 1024).toFixed(2)} KB)
                          </div>
                          <ColumnMappingDialog
                            fileType="calibrations"
                            file={value.calibrationsFile}
                            onMappingChange={(mapping) => handleMappingChange('calibrations', mapping)}
                          />
                        </>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* File Upload */}
        {sourceType === 'upload' && (
          <div className="space-y-4">
            <div className="text-sm text-muted-foreground">
              Upload configuration files (all optional). Default values will be used for missing files.
            </div>

            {/* Metadata File */}
            <div className="space-y-2">
              <Label htmlFor="metadata-file">
                Metadata (CSV/JSON/XLSX)
                <span className="text-xs text-muted-foreground ml-2">Optional</span>
              </Label>
              <Input
                id="metadata-file"
                type="file"
                accept=".csv,.json,.xlsx"
                onChange={(e) => handleFileChange('metadata', e.target.files?.[0] || null)}
              />
              {value.metadataFile && (
                <>
                  <div className="text-xs text-muted-foreground">
                    Selected: {value.metadataFile.name} ({(value.metadataFile.size / 1024).toFixed(2)} KB)
                  </div>
                  <ColumnMappingDialog
                    fileType="metadata"
                    file={value.metadataFile}
                    onMappingChange={(mapping) => handleMappingChange('metadata', mapping)}
                  />
                </>
              )}
              <div className="text-xs text-muted-foreground">
                Sensor deployments: sensor_id, site, treatment, install dates, channel labels
              </div>
            </div>

            {/* QC Params File */}
            <div className="space-y-2">
              <Label htmlFor="qc-params-file">
                QC Parameters (JSON)
                <span className="text-xs text-muted-foreground ml-2">Optional</span>
              </Label>
              <Input
                id="qc-params-file"
                type="file"
                accept=".json"
                onChange={(e) => handleFileChange('qcParams', e.target.files?.[0] || null)}
              />
              {value.qcParamsFile && (
                <div className="text-xs text-muted-foreground">
                  Selected: {value.qcParamsFile.name} ({(value.qcParamsFile.size / 1024).toFixed(2)} KB)
                </div>
              )}
              <div className="text-xs text-muted-foreground">
                QC thresholds for Hampel, flatline, range, rate detection per channel
              </div>
            </div>

            {/* Corrections File */}
            <div className="space-y-2">
              <Label htmlFor="corrections-file">
                Correction Rules (CSV)
                <span className="text-xs text-muted-foreground ml-2">Optional</span>
              </Label>
              <Input
                id="corrections-file"
                type="file"
                accept=".csv"
                onChange={(e) => handleFileChange('corrections', e.target.files?.[0] || null)}
              />
              {value.correctionsFile && (
                <>
                  <div className="text-xs text-muted-foreground">
                    Selected: {value.correctionsFile.name} ({(value.correctionsFile.size / 1024).toFixed(2)} KB)
                  </div>
                  <ColumnMappingDialog
                    fileType="corrections"
                    file={value.correctionsFile}
                    onMappingChange={(mapping) => handleMappingChange('corrections', mapping)}
                  />
                </>
              )}
              <div className="text-xs text-muted-foreground">
                Signal correction rules: sensor_id, correction_type, factor_a, factor_b
              </div>
            </div>

            {/* Calibrations File */}
            <div className="space-y-2">
              <Label htmlFor="calibrations-file">
                Calibration Rules (CSV)
                <span className="text-xs text-muted-foreground ml-2">Optional</span>
              </Label>
              <Input
                id="calibrations-file"
                type="file"
                accept=".csv"
                onChange={(e) => handleFileChange('calibrations', e.target.files?.[0] || null)}
              />
              {value.calibrationsFile && (
                <>
                  <div className="text-xs text-muted-foreground">
                    Selected: {value.calibrationsFile.name} ({(value.calibrationsFile.size / 1024).toFixed(2)} KB)
                  </div>
                  <ColumnMappingDialog
                    fileType="calibrations"
                    file={value.calibrationsFile}
                    onMappingChange={(mapping) => handleMappingChange('calibrations', mapping)}
                  />
                </>
              )}
              <div className="text-xs text-muted-foreground">
                VWC calibration curves: sensor_id, coef_0 to coef_5 (polynomial)
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
