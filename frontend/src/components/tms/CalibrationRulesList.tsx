import { Trash2 } from 'lucide-react';
import { Button } from '../ui/button';
import type { CalibrationRule } from './CalibrationRuleForm';

interface CalibrationRulesListProps {
  rules: Array<CalibrationRule & { index: number }>;
  onDelete: (index: number) => Promise<void>;
  hiddenCount?: number;
}

function formatCoef(v: number | null | undefined): string {
  if (v === null || v === undefined || isNaN(v)) return '';
  return v.toPrecision(6).replace(/\.?0+$/, '');
}

function formatRuleSummary(rule: CalibrationRule): string {
  const sensorId = rule.sensor_id || '*';

  // Format coefficients - only show non-zero/non-null ones
  const coefs = [];
  if (rule.coef_0 !== 0 && rule.coef_0 !== null) coefs.push(`c₀=${formatCoef(rule.coef_0)}`);
  if (rule.coef_1 !== 0 && rule.coef_1 !== null) coefs.push(`c₁=${formatCoef(rule.coef_1)}`);
  if (rule.coef_2 !== 0 && rule.coef_2 !== null) coefs.push(`c₂=${formatCoef(rule.coef_2)}`);
  if (rule.coef_3) coefs.push(`c₃=${formatCoef(rule.coef_3)}`);
  if (rule.coef_4) coefs.push(`c₄=${formatCoef(rule.coef_4)}`);
  if (rule.coef_5) coefs.push(`c₅=${formatCoef(rule.coef_5)}`);

  const coefsStr = coefs.length > 0 ? coefs.join(', ') : 'linear';

  let window = '';
  if (rule.valid_from || rule.valid_to) {
    const from = rule.valid_from || '...';
    const to = rule.valid_to || '...';
    window = ` - ${from} → ${to}`;
  }

  let notes = '';
  if (rule.notes) {
    notes = ` - _${rule.notes}_`;
  }

  return `\`${sensorId}\` - ${coefsStr}${window}${notes}`;
}

export function CalibrationRulesList({
  rules,
  onDelete,
  hiddenCount = 0,
}: CalibrationRulesListProps) {
  if (rules.length === 0 && hiddenCount === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No calibration rules yet - add one above, or upload a file.
      </p>
    );
  }

  if (rules.length === 0 && hiddenCount > 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No calibration rules match the currently loaded sensors.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm font-medium">{rules.length} rule(s)</p>
      {rules.map((rule) => (
        <div key={rule.index} className="flex items-start gap-2">
          <div className="flex-1 text-sm">
            <span dangerouslySetInnerHTML={{ __html: formatRuleSummary(rule).replace(/`([^`]+)`/g, '<code class="bg-muted px-1 rounded text-xs">$1</code>').replace(/_([^_]+)_/g, '<em>$1</em>') }} />
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onDelete(rule.index)}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      ))}
      {hiddenCount > 0 && (
        <p className="text-xs text-muted-foreground">
          {hiddenCount} rule(s) hidden - sensor_id/group not present in the currently loaded data.
        </p>
      )}
    </div>
  );
}
