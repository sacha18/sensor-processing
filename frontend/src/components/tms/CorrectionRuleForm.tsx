import { useState } from 'react';
import { PlusCircle } from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';

export interface CorrectionRule {
  sensor_id: string;
  correction_type: 'one_factor' | 'two_factor';
  factor_a: number;
  factor_b?: number | null;
  valid_from?: string | null;
  valid_to?: string | null;
  notes?: string | null;
}

interface CorrectionRuleFormProps {
  sensorOptions: string[]; // ["*", "sensor1", "sensor2", "group1", ...]
  onSubmit: (rule: CorrectionRule) => Promise<void>;
}

export function CorrectionRuleForm({ sensorOptions, onSubmit }: CorrectionRuleFormProps) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [formData, setFormData] = useState<CorrectionRule>({
    sensor_id: '*',
    correction_type: 'one_factor',
    factor_a: 1.0,
    factor_b: null,
    valid_from: null,
    valid_to: null,
    notes: null,
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // Validation
    if (formData.factor_a === null || formData.factor_a === undefined) {
      setError('"a" is required.');
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit(formData);
      // Reset form
      setFormData({
        sensor_id: '*',
        correction_type: 'one_factor',
        factor_a: 1.0,
        factor_b: null,
        valid_from: null,
        valid_to: null,
        notes: null,
      });
    } catch (err) {
      setError(String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Add a correction rule</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-4 gap-3">
            <div>
              <Label htmlFor="sensor">Sensor or group</Label>
              <Select
                value={formData.sensor_id}
                onValueChange={(value) => setFormData({ ...formData, sensor_id: value })}
              >
                <SelectTrigger id="sensor">
                  <SelectValue placeholder="*" />
                </SelectTrigger>
                <SelectContent>
                  {sensorOptions.map((opt) => (
                    <SelectItem key={opt} value={opt}>
                      {opt}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground mt-1">
                Blank or "*" = every sensor
              </p>
            </div>

            <div>
              <Label htmlFor="type">Type</Label>
              <Select
                value={formData.correction_type}
                onValueChange={(value: 'one_factor' | 'two_factor') =>
                  setFormData({ ...formData, correction_type: value })
                }
              >
                <SelectTrigger id="type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="one_factor">one_factor</SelectItem>
                  <SelectItem value="two_factor">two_factor</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label htmlFor="factor_a">a</Label>
              <Input
                id="factor_a"
                type="number"
                step="any"
                value={formData.factor_a}
                onChange={(e) =>
                  setFormData({ ...formData, factor_a: parseFloat(e.target.value) })
                }
                required
              />
            </div>

            <div>
              <Label htmlFor="factor_b">b</Label>
              <Input
                id="factor_b"
                type="number"
                step="any"
                value={formData.factor_b ?? ''}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    factor_b: e.target.value ? parseFloat(e.target.value) : null,
                  })
                }
              />
              <p className="text-xs text-muted-foreground mt-1">Two-factor only</p>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <Label htmlFor="valid_from">Valid from</Label>
              <Input
                id="valid_from"
                type="date"
                value={formData.valid_from ?? ''}
                onChange={(e) =>
                  setFormData({ ...formData, valid_from: e.target.value || null })
                }
              />
              <p className="text-xs text-muted-foreground mt-1">Blank = always</p>
            </div>

            <div>
              <Label htmlFor="valid_to">Valid to</Label>
              <Input
                id="valid_to"
                type="date"
                value={formData.valid_to ?? ''}
                onChange={(e) =>
                  setFormData({ ...formData, valid_to: e.target.value || null })
                }
              />
              <p className="text-xs text-muted-foreground mt-1">Blank = always</p>
            </div>

            <div>
              <Label htmlFor="notes">Notes</Label>
              <Input
                id="notes"
                type="text"
                value={formData.notes ?? ''}
                onChange={(e) =>
                  setFormData({ ...formData, notes: e.target.value || null })
                }
              />
            </div>
          </div>

          {error && (
            <div className="text-sm text-destructive">{error}</div>
          )}

          <Button type="submit" disabled={submitting} className="w-full">
            <PlusCircle className="h-4 w-4 mr-2" />
            {submitting ? 'Adding...' : 'Add rule'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
