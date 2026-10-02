export type ColumnMapping = {
  [expectedColumn: string]: string; // expectedColumn -> actualColumn from file
};

export type ConfigSource = {
  type: 'dataset' | 'upload';
  datasetId?: string;
  // For hybrid mode: which config items to import from dataset
  useDatasetMetadata?: boolean;
  useDatasetQcParams?: boolean;
  useDatasetCorrections?: boolean;
  useDatasetCalibrations?: boolean;
  // Manual uploads (used when not importing from dataset, or in hybrid mode)
  metadataFile?: File;
  qcParamsFile?: File;
  correctionsFile?: File;
  calibrationsFile?: File;
  // Column mappings for uploaded files
  metadataMapping?: ColumnMapping;
  correctionsMapping?: ColumnMapping;
  calibrationsMapping?: ColumnMapping;
}
