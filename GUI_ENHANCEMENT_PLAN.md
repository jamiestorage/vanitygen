# Immediate GUI Enhancement Plan for GPU/CPU Mode Selection

## Overview

While the full GPU acceleration implementation is a long-term project, we can provide immediate value by enhancing the GUI to give users better control over the current GPU/CPU functionality and clearer understanding of what each mode does.

## Current Situation

### Current GUI Options:
- **CPU Mode**: Uses CPU for all operations (key generation + cryptographic operations)
- **GPU Mode**: Uses GPU for key generation, CPU for cryptographic operations

### User Confusion:
- Users expect "GPU Mode" to offload most work to GPU
- Current implementation still uses significant CPU resources
- No clear explanation of what each mode actually does
- No performance metrics to help users make informed choices

## Immediate Enhancement Plan

### 1. Enhanced Mode Selection with Clear Descriptions

```python
# Add to GUI settings tab
gpu_mode_group = QGroupBox("Acceleration Mode")
gpu_mode_layout = QVBoxLayout()

# Mode selection with clear descriptions
self.mode_combo = QComboBox()
self.mode_combo.addItem("CPU Only - Uses CPU for all operations")
self.mode_combo.addItem("GPU Key Generation - GPU generates keys, CPU processes them")
self.mode_combo.addItem("Balanced - Optimized mix of GPU and CPU")

# Add tooltips for more detailed explanations
self.mode_combo.setItemData(0, 
    "CPU Only: Uses only CPU resources. Good for systems without GPU or when GPU is busy.",
    Qt.ToolTipRole)

self.mode_combo.setItemData(1,
    "GPU Key Generation: GPU generates random keys quickly, but CPU still handles the expensive cryptographic operations. "
    "This is the current default GPU mode and uses significant CPU resources.",
    Qt.ToolTipRole)

self.mode_combo.setItemData(2,
    "Balanced: Uses GPU for key generation but limits CPU usage for post-processing. "
    "Provides a good balance between performance and resource usage.",
    Qt.ToolTipRole)

gpu_mode_layout.addWidget(self.mode_combo)
gpu_mode_group.setLayout(gpu_mode_layout)
```

### 2. CPU Core Configuration for GPU Mode

```python
# Add CPU core selection for GPU mode
cpu_cores_group = QGroupBox("CPU Resource Allocation")
cpu_cores_layout = QVBoxLayout()

self.cpu_cores_label = QLabel("CPU Cores for GPU Mode Post-Processing:")
self.cpu_cores_slider = QSlider(Qt.Horizontal)
self.cpu_cores_slider.setRange(1, multiprocessing.cpu_count())
self.cpu_cores_slider.setValue(2)  # Default to 2 cores

self.cpu_cores_value = QLabel("2 cores")

# Connect slider to update label
self.cpu_cores_slider.valueChanged.connect(
    lambda value: self.cpu_cores_value.setText(f"{value} cores")
)

cpu_cores_layout.addWidget(self.cpu_cores_label)
cpu_cores_layout.addWidget(self.cpu_cores_slider)
cpu_cores_layout.addWidget(self.cpu_cores_value)
cpu_cores_group.setLayout(cpu_cores_layout)
```

### 3. Real-time Resource Monitoring

```python
# Add resource monitoring to status bar
resource_monitor = QHBoxLayout()

self.cpu_usage_label = QLabel("CPU: 0%")
self.gpu_usage_label = QLabel("GPU: 0%")
self.memory_label = QLabel("Mem: 0 MB")

resource_monitor.addWidget(self.cpu_usage_label)
resource_monitor.addWidget(self.gpu_usage_label)
resource_monitor.addWidget(self.memory_label)

# Add to status bar
self.statusBar().addPermanentWidget(QLabel("|"))
for widget in [self.cpu_usage_label, self.gpu_usage_label, self.memory_label]:
    self.statusBar().addPermanentWidget(widget)

# Update function
def update_resource_monitoring(self):
    """Update resource usage displays"""
    if not hasattr(self, 'monitor_timer') or not self.monitor_timer.isActive():
        return
    
    try:
        # Get CPU usage
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # Get GPU usage (if available)
        gpu_percent = 0
        try:
            if hasattr(psutil, 'gpu_percent'):
                gpu_percent = psutil.gpu_percent(interval=0.1)
            elif hasattr(self, 'generator') and hasattr(self.generator, 'device'):
                # Try OpenCL-based GPU monitoring
                gpu_percent = self._get_opencl_gpu_usage()
        except:
            pass
        
        # Get memory usage
        memory_info = psutil.virtual_memory()
        memory_usage = memory_info.used // 1024 // 1024  # MB
        
        # Update UI
        self.cpu_usage_label.setText(f"CPU: {cpu_percent}%")
        self.gpu_usage_label.setText(f"GPU: {gpu_percent}%")
        self.memory_label.setText(f"Mem: {memory_usage} MB")
        
    except Exception as e:
        print(f"Resource monitoring error: {e}")
```

### 4. Performance Metrics Display

```python
# Add performance metrics tab
performance_tab = QWidget()
performance_layout = QVBoxLayout()

# Performance chart
self.performance_chart = QChart()
self.performance_chart.setTitle("Performance Metrics")
self.performance_chart.setAnimationOptions(QChart.AllAnimations)

self.performance_view = QChartView(self.performance_chart)
self.performance_view.setRenderHint(QPainter.Antialiasing)

# Add series for different metrics
self.cpu_series = QLineSeries()
self.cpu_series.setName("CPU Usage")
self.gpu_series = QLineSeries()
self.gpu_series.setName("GPU Usage")
self.speed_series = QLineSeries()
self.speed_series.setName("Keys/Second")

self.performance_chart.addSeries(self.cpu_series)
self.performance_chart.addSeries(self.gpu_series)
self.performance_chart.addSeries(self.speed_series)

# Create axis
axis_x = QValueAxis()
axis_x.setTitleText("Time (seconds)")
axis_x.setLabelFormat("%d")
axis_x.setTickCount(5)

axis_y = QValueAxis()
axis_y.setTitleText("Usage / Performance")
axis_y.setLabelFormat("%d")
axis_y.setRange(0, 100)

self.performance_chart.addAxis(axis_x, Qt.AlignBottom)
self.performance_chart.addAxis(axis_y, Qt.AlignLeft)

self.cpu_series.attachAxis(axis_x)
self.cpu_series.attachAxis(axis_y)
self.gpu_series.attachAxis(axis_x)
self.gpu_series.attachAxis(axis_y)

# Add secondary axis for speed
axis_y2 = QValueAxis()
axis_y2.setTitleText("Keys/Second")
axis_y2.setLabelFormat("%d")
axis_y2.setRange(0, 1000000)
self.performance_chart.addAxis(axis_y2, Qt.AlignRight)
self.speed_series.attachAxis(axis_x)
self.speed_series.attachAxis(axis_y2)

performance_layout.addWidget(self.performance_view)
performance_tab.setLayout(performance_layout)

# Add to main tab widget
self.tabs.addTab(performance_tab, "Performance")
```

### 5. Mode-Specific Recommendations

```python
def get_mode_recommendation(self):
    """Provide recommendations based on hardware and workload"""
    recommendation = ""
    
    try:
        # Get system information
        cpu_cores = multiprocessing.cpu_count()
        total_memory = psutil.virtual_memory().total // 1024 // 1024 // 1024  # GB
        
        # Check for GPU
        gpu_available = False
        gpu_info = ""
        try:
            platforms = cl.get_platforms()
            for platform in platforms:
                gpus = platform.get_devices(device_type=cl.device_type.GPU)
                if gpus:
                    gpu_available = True
                    gpu_info = f" ({gpus[0].name})"
                    break
        except:
            pass
        
        # Generate recommendation
        if not gpu_available:
            recommendation = (
                "💡 Recommendation: CPU Only mode is recommended since no compatible GPU was detected.\n\n"
                f"System: {cpu_cores} CPU cores, {total_memory}GB RAM\n"
                "Performance: Good for basic vanity address generation"
            )
        else:
            if self.prefix_length <= 4:
                recommendation = (
                    f"💡 Recommendation: GPU Key Generation mode is recommended for short prefixes.\n\n"
                    f"System: {cpu_cores} CPU cores, {total_memory}GB RAM, GPU{gpu_info}\n"
                    "Performance: GPU acceleration provides good speedup for shorter prefixes"
                )
            else:
                recommendation = (
                    f"💡 Recommendation: Balanced mode is recommended for longer prefixes.\n\n"
                    f"System: {cpu_cores} CPU cores, {total_memory}GB RAM, GPU{gpu_info}\n"
                    "Performance: Balanced mode provides better resource utilization for complex searches"
                )
    
    except Exception as e:
        recommendation = f"💡 Recommendation: Could not determine optimal mode ({e})"
    
    return recommendation
```

### 6. Enhanced Startup Information

```python
def show_startup_info(self):
    """Show detailed information when starting generation"""
    mode_info = ""
    
    if self.mode == 'cpu':
        mode_info = (
            "🔧 CPU Only Mode\n"
            "- Uses CPU for all operations\n"
            "- Good for systems without GPU or when GPU is busy\n"
            "- Lower power consumption\n"
        )
    elif self.mode == 'gpu':
        mode_info = (
            "🔧 GPU Key Generation Mode\n"
            "- GPU generates random keys quickly\n"
            "- CPU handles cryptographic operations\n"
            "- Uses significant CPU resources\n"
            f"- Using {self.cpu_cores} CPU cores for post-processing\n"
        )
    elif self.mode == 'balanced':
        mode_info = (
            "🔧 Balanced Mode\n"
            "- GPU generates random keys\n"
            "- Limited CPU usage for post-processing\n"
            "- Good balance between speed and resource usage\n"
            f"- Using {self.cpu_cores} CPU cores for post-processing\n"
        )
    
    # Show in status area
    self.status_text.append(mode_info)
    self.status_text.append(self.get_mode_recommendation())
```

## Implementation Steps

### Step 1: Add Required Dependencies

```bash
# Add psutil for system monitoring
pip install psutil
```

### Step 2: Update GUI Layout

```python
# In __init__ method of VanityGenGUI
self._setup_acceleration_settings()
self._setup_resource_monitoring()
self._setup_performance_metrics()
```

### Step 3: Connect Signals and Slots

```python
# Connect mode selection
self.mode_combo.currentIndexChanged.connect(self._update_mode_settings)

# Connect CPU cores slider
self.cpu_cores_slider.valueChanged.connect(
    lambda value: setattr(self, 'selected_cpu_cores', value)
)

# Start resource monitoring timer
self.monitor_timer = QTimer()
self.monitor_timer.timeout.connect(self.update_resource_monitoring)
self.monitor_timer.start(1000)  # Update every second
```

### Step 4: Update Generator Creation

```python
# In GeneratorThread.__init__
def __init__(self, prefix, addr_type, balance_checker, auto_resume=False,
             mode='cpu', case_insensitive=False, batch_size=4096, 
             cpu_cores=None, gpu_power_percent=100, gpu_device_selector=None):
    # ... existing code ...
    self.cpu_cores = cpu_cores if cpu_cores is not None else 2
    
    # Map mode to generator type
    if mode == 'gpu':
        self.generator = GPUGenerator(
            self.prefix, self.addr_type, batch_size=self.batch_size,
            power_percent=self.gpu_power_percent,
            device_selector=self.gpu_device_selector,
            cpu_cores=self.cpu_cores
        )
    elif mode == 'balanced':
        # Balanced mode uses GPU with limited CPU cores
        self.generator = GPUGenerator(
            self.prefix, self.addr_type, batch_size=self.batch_size,
            power_percent=self.gpu_power_percent,
            device_selector=self.gpu_device_selector,
            cpu_cores=min(2, self.cpu_cores)  # Limit to 2 cores for balanced mode
        )
    else:  # cpu mode
        self.generator = CPUGenerator(
            self.prefix, self.addr_type, cores=self.cpu_cores,
            case_insensitive=self.case_insensitive
        )
```

## Expected Benefits

### 1. Better User Understanding
- Clear explanations of what each mode actually does
- Real-time feedback on resource usage
- Performance metrics to help users optimize

### 2. Improved Resource Management
- Users can limit CPU usage in GPU mode
- Better control over system resource allocation
- Reduced impact on other running applications

### 3. Enhanced User Experience
- Visual performance monitoring
- Mode recommendations based on hardware
- Clear startup information

### 4. Foundation for Future Enhancements
- Performance data collection for optimization
- User interface ready for true GPU acceleration
- Better debugging and troubleshooting capabilities

## Implementation Timeline

| Task | Duration | Priority |
|------|----------|----------|
| Add dependencies | 1 day | High |
| Update GUI layout | 2-3 days | High |
| Implement resource monitoring | 2-3 days | High |
| Add performance metrics | 3-4 days | Medium |
| Enhance startup info | 1-2 days | Medium |
| Testing and bug fixing | 3-5 days | High |
| **Total** | **2-3 weeks** | **Complete enhancement** |

## Backward Compatibility

All changes are backward compatible:
- Existing code continues to work
- Default behavior remains similar
- New features are opt-in
- GUI enhancements don't break existing functionality

## Conclusion

This immediate GUI enhancement provides significant value to users by:
1. **Clarifying** what each acceleration mode actually does
2. **Giving users control** over CPU resource usage in GPU mode
3. **Providing performance feedback** to help users optimize their setup
4. **Laying the foundation** for future true GPU acceleration

The enhancement can be implemented in 2-3 weeks and provides immediate benefits while setting the stage for the more comprehensive true GPU acceleration project.