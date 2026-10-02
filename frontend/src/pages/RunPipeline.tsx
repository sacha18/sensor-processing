import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Zap, Settings } from 'lucide-react';
import { QuickStartForm } from '../components/run/QuickStartForm';
import { AutomatedRunForm } from '../components/run/AutomatedRunForm';

export function RunPipeline() {
  return (
    <div className="container mx-auto py-8 max-w-4xl">
      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-2">Run Pipeline</h1>
        <p className="text-muted-foreground">
          Upload sensor data and process it through the cleaning pipeline
        </p>
      </div>

      <Tabs defaultValue="quick-start" className="w-full">
        <TabsList className="grid w-full grid-cols-2 mb-6">
          <TabsTrigger value="quick-start" className="flex items-center gap-2">
            <Zap className="h-4 w-4" />
            Quick Start
          </TabsTrigger>
          <TabsTrigger value="automated" className="flex items-center gap-2">
            <Settings className="h-4 w-4" />
            Automated Run
          </TabsTrigger>
        </TabsList>

        <TabsContent value="quick-start">
          <div className="space-y-4">
            <div className="p-4 bg-muted rounded-md text-sm">
              <p className="font-medium mb-1">Quick Start Mode</p>
              <p className="text-muted-foreground">
                Upload your data and configure parameters step-by-step in the interactive wizard.
                Perfect for exploring and fine-tuning your pipeline.
              </p>
            </div>
            <QuickStartForm />
          </div>
        </TabsContent>

        <TabsContent value="automated">
          <div className="space-y-4">
            <div className="p-4 bg-muted rounded-md text-sm">
              <p className="font-medium mb-1">Automated Run Mode</p>
              <p className="text-muted-foreground">
                Upload data with pre-configured parameters for hands-off processing.
                Ideal for large datasets or repeating previous configurations.
              </p>
            </div>
            <AutomatedRunForm />
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
