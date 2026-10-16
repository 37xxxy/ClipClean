using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Windows.Forms;

namespace AdSkipLocal
{
    internal sealed class Job
    {
        public int RowIndex;
        public string Input;
        public string Output;
        public string Report;
        public string PreviewDirectory;
        public string Log;
    }

    internal sealed class JobUpdate
    {
        public int RowIndex;
        public string Status;
        public string Output;
        public string Detail;
    }

    internal sealed class ProcessingOptions
    {
        public bool FullScan;
        public decimal SearchStartPercent;
        public decimal SearchEndPercent;
        public int LeadingGuardFrames;
        public int TrailingGuardFrames;
        public int SafetyGuardFrames;
    }

    internal sealed class ReferenceDialog : Form
    {
        private readonly TextBox sourceText = new TextBox();
        private readonly TextBox outputText = new TextBox();
        private readonly NumericUpDown startTime = new NumericUpDown();
        private readonly NumericUpDown endTime = new NumericUpDown();

        public string SourcePath { get { return sourceText.Text.Trim(); } }
        public string OutputPath { get { return outputText.Text.Trim(); } }
        public decimal StartSeconds { get { return startTime.Value; } }
        public decimal EndSeconds { get { return endTime.Value; } }

        public ReferenceDialog(string initialOutputDirectory)
        {
            Text = "制作广告基准";
            Font = new Font("Microsoft YaHei UI", 9F);
            BackColor = Color.FromArgb(246, 248, 249);
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;
            ShowInTaskbar = false;
            StartPosition = FormStartPosition.CenterParent;
            ClientSize = new Size(650, 330);

            var header = new Panel { Dock = DockStyle.Top, Height = 72, BackColor = Color.White };
            header.Controls.Add(new Label
            {
                Text = "从一段视频中截取固定广告",
                Font = new Font("Microsoft YaHei UI", 15F, FontStyle.Bold),
                AutoSize = true,
                Location = new Point(24, 13)
            });
            header.Controls.Add(new Label
            {
                Text = "开始填广告第一帧的时间，结束填广告后第一帧的时间。",
                ForeColor = Color.FromArgb(92, 101, 110),
                AutoSize = true,
                Location = new Point(27, 44)
            });
            Controls.Add(header);

            AddLabel("来源视频", 28, 99);
            sourceText.Location = new Point(112, 94);
            sourceText.Size = new Size(414, 28);
            Controls.Add(sourceText);
            var browse = MakeButton("选择", 78);
            browse.Location = new Point(540, 92);
            browse.Click += delegate
            {
                using (var dialog = new OpenFileDialog())
                {
                    dialog.Filter = "视频文件|*.mp4;*.mkv;*.mov;*.m4v;*.avi;*.ts;*.mts;*.m2ts|所有文件|*.*";
                    if (dialog.ShowDialog(this) == DialogResult.OK)
                    {
                        sourceText.Text = dialog.FileName;
                        if (String.IsNullOrWhiteSpace(outputText.Text))
                        {
                            outputText.Text = Path.Combine(
                                initialOutputDirectory,
                                Path.GetFileNameWithoutExtension(dialog.FileName) + "-ad-reference.mp4"
                            );
                        }
                    }
                }
            };
            Controls.Add(browse);

            AddLabel("广告时间", 28, 151);
            ConfigureTime(startTime);
            ConfigureTime(endTime);
            startTime.Location = new Point(112, 146);
            endTime.Location = new Point(260, 146);
            Controls.Add(startTime);
            Controls.Add(endTime);
            Controls.Add(new Label { Text = "秒  至", AutoSize = true, Location = new Point(214, 151) });
            Controls.Add(new Label { Text = "秒", AutoSize = true, Location = new Point(362, 151) });
            var openSource = MakeButton("打开视频", 94);
            openSource.Location = new Point(420, 143);
            openSource.Click += delegate
            {
                if (File.Exists(SourcePath))
                    Process.Start(new ProcessStartInfo(SourcePath) { UseShellExecute = true });
            };
            Controls.Add(openSource);

            AddLabel("保存为", 28, 203);
            outputText.Location = new Point(112, 198);
            outputText.Size = new Size(414, 28);
            outputText.Text = Path.Combine(initialOutputDirectory, "ad-reference.mp4");
            Controls.Add(outputText);
            var saveAs = MakeButton("选择", 78);
            saveAs.Location = new Point(540, 196);
            saveAs.Click += delegate
            {
                using (var dialog = new SaveFileDialog())
                {
                    dialog.Filter = "MP4 视频|*.mp4";
                    dialog.FileName = Path.GetFileName(outputText.Text);
                    dialog.InitialDirectory = Path.GetDirectoryName(outputText.Text);
                    if (dialog.ShowDialog(this) == DialogResult.OK) outputText.Text = dialog.FileName;
                }
            };
            Controls.Add(saveAs);

            var cancel = MakeButton("取消", 86);
            cancel.Location = new Point(438, 270);
            cancel.DialogResult = DialogResult.Cancel;
            var create = MakeButton("生成基准", 100);
            create.Location = new Point(536, 270);
            create.BackColor = Color.FromArgb(18, 137, 117);
            create.ForeColor = Color.White;
            create.FlatAppearance.BorderSize = 0;
            create.Click += delegate
            {
                if (!File.Exists(SourcePath))
                {
                    MessageBox.Show(this, "请选择有效的来源视频。", "来源视频无效");
                    return;
                }
                if (EndSeconds <= StartSeconds)
                {
                    MessageBox.Show(this, "结束时间必须大于开始时间。", "时间范围无效");
                    return;
                }
                if (File.Exists(OutputPath))
                {
                    MessageBox.Show(this, "保存位置已有同名文件，请换一个名称。", "文件已存在");
                    return;
                }
                DialogResult = DialogResult.OK;
                Close();
            };
            Controls.Add(cancel);
            Controls.Add(create);
            AcceptButton = create;
            CancelButton = cancel;
        }

        private void AddLabel(string text, int left, int top)
        {
            Controls.Add(new Label
            {
                Text = text,
                ForeColor = Color.FromArgb(66, 75, 84),
                AutoSize = true,
                Location = new Point(left, top)
            });
        }

        private static void ConfigureTime(NumericUpDown input)
        {
            input.Minimum = 0;
            input.Maximum = 86400;
            input.DecimalPlaces = 3;
            input.Increment = 0.04M;
            input.Width = 96;
            input.TextAlign = HorizontalAlignment.Right;
        }

        private static Button MakeButton(string text, int width)
        {
            var button = new Button
            {
                Text = text,
                Size = new Size(width, 34),
                FlatStyle = FlatStyle.Flat,
                BackColor = Color.White
            };
            button.FlatAppearance.BorderColor = Color.FromArgb(190, 198, 204);
            return button;
        }
    }

    internal sealed class MainForm : Form
    {
        private const string AppVersion = "0.3.0";
        private static readonly HashSet<string> VideoExtensions = new HashSet<string>(
            new[] { ".mp4", ".mkv", ".mov", ".m4v", ".avi", ".ts", ".mts", ".m2ts" },
            StringComparer.OrdinalIgnoreCase
        );

        private readonly string appRoot;
        private readonly string settingsPath;
        private readonly string legacySettingsPath;
        private readonly TextBox adText = new TextBox();
        private readonly TextBox outputText = new TextBox();
        private readonly Label profileStatus = new Label();
        private readonly Button createReferenceButton = new Button();
        private readonly ComboBox searchMode = new ComboBox();
        private readonly NumericUpDown searchStart = new NumericUpDown();
        private readonly NumericUpDown searchEnd = new NumericUpDown();
        private readonly ComboBox cutPreset = new ComboBox();
        private readonly NumericUpDown leadingGuard = new NumericUpDown();
        private readonly NumericUpDown trailingGuard = new NumericUpDown();
        private readonly NumericUpDown safetyGuard = new NumericUpDown();
        private readonly Label searchRangeLabel = new Label();
        private readonly Label guardSummary = new Label();
        private readonly DataGridView queue = new DataGridView();
        private readonly ProgressBar progress = new ProgressBar();
        private readonly Label status = new Label();
        private readonly Button startButton = new Button();
        private readonly Button cancelButton = new Button();
        private readonly Button addButton = new Button();
        private readonly Button removeButton = new Button();
        private readonly Button clearButton = new Button();
        private readonly Button openResultButton = new Button();
        private readonly BackgroundWorker worker = new BackgroundWorker();
        private Process activeProcess;

        public MainForm()
        {
            appRoot = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
            string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            settingsPath = Path.Combine(localAppData, "ClipClean", "settings.txt");
            legacySettingsPath = Path.Combine(localAppData, "AdSkip Local", "settings.txt");

            Text = "ClipClean v" + AppVersion + " - 固定广告清理工具";
            MinimumSize = new Size(900, 680);
            Size = new Size(1040, 760);
            StartPosition = FormStartPosition.CenterScreen;
            Font = new Font("Microsoft YaHei UI", 9F, FontStyle.Regular, GraphicsUnit.Point);
            BackColor = Color.FromArgb(242, 245, 247);
            AllowDrop = true;
            AutoScaleMode = AutoScaleMode.Dpi;

            BuildLayout();
            LoadSettings();
            ConfigureWorker();

            DragEnter += HandleDragEnter;
            DragDrop += HandleDragDrop;
            FormClosing += HandleFormClosing;
        }

        private void BuildLayout()
        {
            var header = new Panel { Dock = DockStyle.Top, Height = 92, BackColor = Color.White };
            var mark = new Label
            {
                Text = "AS",
                TextAlign = ContentAlignment.MiddleCenter,
                Font = new Font("Segoe UI", 13F, FontStyle.Bold),
                ForeColor = Color.White,
                BackColor = Color.FromArgb(18, 137, 117),
                Size = new Size(46, 46),
                Location = new Point(26, 22)
            };
            var title = new Label
            {
                Text = "ClipClean",
                Font = new Font("Microsoft YaHei UI", 19F, FontStyle.Bold),
                ForeColor = Color.FromArgb(28, 36, 43),
                AutoSize = true,
                Location = new Point(86, 17)
            };
            var subtitle = new Label
            {
                Text = "本地视频片段清理  ·  v" + AppVersion,
                ForeColor = Color.FromArgb(93, 103, 112),
                AutoSize = true,
                Location = new Point(89, 55)
            };
            var safety = new Label
            {
                Text = "原视频不会被覆盖",
                TextAlign = ContentAlignment.MiddleCenter,
                ForeColor = Color.FromArgb(18, 111, 80),
                BackColor = Color.FromArgb(231, 247, 240),
                Size = new Size(126, 28),
                Anchor = AnchorStyles.Top | AnchorStyles.Right,
                Location = new Point(Width - 174, 31)
            };
            header.Resize += delegate { safety.Left = header.ClientSize.Width - safety.Width - 26; };
            header.Controls.Add(mark);
            header.Controls.Add(title);
            header.Controls.Add(subtitle);
            header.Controls.Add(safety);

            var setup = new Panel
            {
                Dock = DockStyle.Top,
                Height = 208,
                BackColor = Color.FromArgb(242, 245, 247)
            };
            var sourcePanel = new Panel
            {
                BackColor = Color.White,
                Location = new Point(26, 15),
                Size = new Size(570, 178),
                Anchor = AnchorStyles.Left | AnchorStyles.Top | AnchorStyles.Right
            };
            var optionsPanel = new Panel
            {
                BackColor = Color.White,
                Size = new Size(382, 178),
                Location = new Point(setup.Width - 408, 15),
                Anchor = AnchorStyles.Top | AnchorStyles.Right
            };
            setup.Resize += delegate
            {
                optionsPanel.Left = setup.ClientSize.Width - optionsPanel.Width - 26;
                sourcePanel.Width = Math.Max(380, optionsPanel.Left - sourcePanel.Left - 14);
            };

            sourcePanel.Controls.Add(SectionTitle("1  基础设置", new Point(18, 14)));
            sourcePanel.Controls.Add(FieldCaption("广告基准", new Point(18, 49)));
            adText.Location = new Point(100, 45);
            adText.Height = 28;
            adText.Anchor = AnchorStyles.Left | AnchorStyles.Top | AnchorStyles.Right;
            adText.Width = sourcePanel.Width - 304;
            adText.TextChanged += delegate { UpdateProfileStatus(); };
            var browseAd = CreateCompactButton("选择", 66);
            browseAd.Anchor = AnchorStyles.Top | AnchorStyles.Right;
            browseAd.Location = new Point(sourcePanel.Width - 194, 43);
            browseAd.Click += BrowseAd;
            createReferenceButton.Text = "制作基准";
            StyleCommandButton(createReferenceButton, 94);
            createReferenceButton.Anchor = AnchorStyles.Top | AnchorStyles.Right;
            createReferenceButton.Location = new Point(sourcePanel.Width - 112, 43);
            createReferenceButton.Click += CreateReference;
            profileStatus.AutoSize = true;
            profileStatus.Location = new Point(101, 76);
            sourcePanel.Resize += delegate
            {
                adText.Width = Math.Max(100, sourcePanel.ClientSize.Width - 304);
                browseAd.Left = sourcePanel.ClientSize.Width - 194;
                createReferenceButton.Left = sourcePanel.ClientSize.Width - 112;
            };
            sourcePanel.Controls.Add(adText);
            sourcePanel.Controls.Add(browseAd);
            sourcePanel.Controls.Add(createReferenceButton);
            sourcePanel.Controls.Add(profileStatus);

            sourcePanel.Controls.Add(FieldCaption("输出目录", new Point(18, 113)));
            outputText.Location = new Point(100, 109);
            outputText.Height = 28;
            outputText.Anchor = AnchorStyles.Left | AnchorStyles.Top | AnchorStyles.Right;
            outputText.Width = sourcePanel.Width - 212;
            var browseOutput = CreateCompactButton("选择目录", 84);
            browseOutput.Anchor = AnchorStyles.Top | AnchorStyles.Right;
            browseOutput.Location = new Point(sourcePanel.Width - 102, 107);
            browseOutput.Click += BrowseOutput;
            sourcePanel.Resize += delegate
            {
                outputText.Width = Math.Max(100, sourcePanel.ClientSize.Width - 212);
                browseOutput.Left = sourcePanel.ClientSize.Width - 102;
            };
            sourcePanel.Controls.Add(outputText);
            sourcePanel.Controls.Add(browseOutput);

            optionsPanel.Controls.Add(SectionTitle("检测与切除", new Point(18, 14)));
            optionsPanel.Controls.Add(FieldCaption("搜索区域", new Point(18, 50)));
            searchMode.DropDownStyle = ComboBoxStyle.DropDownList;
            searchMode.Items.AddRange(new object[] { "中间 30%（推荐）", "自定义范围", "扫描整段" });
            searchMode.Location = new Point(100, 46);
            searchMode.Size = new Size(160, 28);
            searchMode.SelectedIndexChanged += SearchModeChanged;
            optionsPanel.Controls.Add(searchMode);
            searchRangeLabel.AutoSize = true;
            searchRangeLabel.ForeColor = Color.FromArgb(92, 101, 110);
            searchRangeLabel.Location = new Point(270, 51);
            optionsPanel.Controls.Add(searchRangeLabel);

            ConfigurePercentInput(searchStart, 35);
            ConfigurePercentInput(searchEnd, 65);
            searchStart.Location = new Point(100, 78);
            searchEnd.Location = new Point(188, 78);
            searchStart.ValueChanged += delegate { UpdateOptionSummary(); };
            searchEnd.ValueChanged += delegate { UpdateOptionSummary(); };
            optionsPanel.Controls.Add(searchStart);
            optionsPanel.Controls.Add(searchEnd);

            optionsPanel.Controls.Add(FieldCaption("切除余量", new Point(18, 115)));
            cutPreset.DropDownStyle = ComboBoxStyle.DropDownList;
            cutPreset.Items.AddRange(new object[] { "推荐", "更少切除", "更强清除", "自定义" });
            cutPreset.Location = new Point(100, 111);
            cutPreset.Size = new Size(120, 28);
            cutPreset.SelectedIndexChanged += CutPresetChanged;
            optionsPanel.Controls.Add(cutPreset);
            ConfigureFrameInput(leadingGuard, 3);
            ConfigureFrameInput(trailingGuard, 2);
            ConfigureFrameInput(safetyGuard, 1);
            leadingGuard.Location = new Point(230, 111);
            trailingGuard.Location = new Point(278, 111);
            safetyGuard.Location = new Point(326, 111);
            optionsPanel.Controls.Add(leadingGuard);
            optionsPanel.Controls.Add(trailingGuard);
            optionsPanel.Controls.Add(safetyGuard);
            guardSummary.AutoSize = true;
            guardSummary.ForeColor = Color.FromArgb(92, 101, 110);
            guardSummary.Location = new Point(100, 145);
            optionsPanel.Controls.Add(guardSummary);

            setup.Controls.Add(sourcePanel);
            setup.Controls.Add(optionsPanel);

            var queueHeader = new Panel { Dock = DockStyle.Top, Height = 56, Padding = new Padding(26, 10, 26, 8) };
            var queueTitle = new Label
            {
                Text = "2  待处理视频",
                Font = new Font("Microsoft YaHei UI", 11F, FontStyle.Bold),
                ForeColor = Color.FromArgb(35, 44, 52),
                AutoSize = true,
                Location = new Point(26, 17)
            };
            addButton.Text = "添加视频";
            removeButton.Text = "移除";
            clearButton.Text = "清空";
            openResultButton.Text = "打开结果";
            StyleCommandButton(addButton, 92);
            StyleCommandButton(removeButton, 72);
            StyleCommandButton(clearButton, 72);
            StyleCommandButton(openResultButton, 88);
            addButton.Click += BrowseVideos;
            removeButton.Click += RemoveSelected;
            clearButton.Click += delegate { if (!worker.IsBusy) queue.Rows.Clear(); };
            openResultButton.Click += OpenSelectedResult;

            var queueCommands = new FlowLayoutPanel
            {
                Dock = DockStyle.Right,
                Width = 354,
                FlowDirection = FlowDirection.LeftToRight,
                WrapContents = false,
                Padding = new Padding(0)
            };
            queueCommands.Controls.Add(addButton);
            queueCommands.Controls.Add(removeButton);
            queueCommands.Controls.Add(clearButton);
            queueCommands.Controls.Add(openResultButton);
            queueHeader.Controls.Add(queueTitle);
            queueHeader.Controls.Add(queueCommands);

            ConfigureQueue();
            var queueHost = new Panel { Dock = DockStyle.Fill, Padding = new Padding(26, 0, 26, 14) };
            queueHost.Controls.Add(queue);

            var footer = new Panel
            {
                Dock = DockStyle.Bottom,
                Height = 116,
                Padding = new Padding(26, 14, 26, 16),
                BackColor = Color.White
            };
            progress.Dock = DockStyle.Top;
            progress.Height = 7;
            progress.Style = ProgressBarStyle.Continuous;
            status.Text = "拖入视频后，点击右下角开始清理。";
            status.AutoEllipsis = true;
            status.ForeColor = Color.FromArgb(72, 78, 86);
            status.Location = new Point(26, 36);
            status.Size = new Size(650, 25);

            startButton.Text = "开始清理";
            startButton.Font = new Font("Microsoft YaHei UI", 10.5F, FontStyle.Bold);
            startButton.BackColor = Color.FromArgb(18, 137, 117);
            startButton.ForeColor = Color.White;
            startButton.FlatStyle = FlatStyle.Flat;
            startButton.FlatAppearance.BorderSize = 0;
            startButton.Size = new Size(132, 42);
            startButton.Anchor = AnchorStyles.Right | AnchorStyles.Top;
            startButton.Location = new Point(Width - 174, 57);
            startButton.Click += StartProcessing;

            cancelButton.Text = "停止";
            cancelButton.Enabled = false;
            cancelButton.FlatStyle = FlatStyle.Flat;
            cancelButton.Size = new Size(76, 42);
            cancelButton.Anchor = AnchorStyles.Right | AnchorStyles.Top;
            cancelButton.Location = new Point(Width - 258, 57);
            cancelButton.Click += CancelProcessing;

            var openOutput = CreateButton("打开输出目录");
            openOutput.Dock = DockStyle.None;
            openOutput.Size = new Size(116, 32);
            openOutput.Location = new Point(26, 68);
            openOutput.Anchor = AnchorStyles.Left | AnchorStyles.Top;
            openOutput.Click += OpenOutputDirectory;

            footer.Controls.Add(progress);
            footer.Controls.Add(status);
            footer.Controls.Add(openOutput);
            footer.Controls.Add(cancelButton);
            footer.Controls.Add(startButton);
            footer.Resize += delegate
            {
                startButton.Left = footer.ClientSize.Width - startButton.Width - 26;
                cancelButton.Left = startButton.Left - cancelButton.Width - 8;
                startButton.Top = 59;
                cancelButton.Top = 59;
            };

            Controls.Add(queueHost);
            Controls.Add(queueHeader);
            Controls.Add(setup);
            Controls.Add(header);
            Controls.Add(footer);
        }

        private void ConfigureQueue()
        {
            queue.Dock = DockStyle.Fill;
            queue.BackgroundColor = Color.White;
            queue.BorderStyle = BorderStyle.None;
            queue.CellBorderStyle = DataGridViewCellBorderStyle.SingleHorizontal;
            queue.GridColor = Color.FromArgb(229, 233, 236);
            queue.AllowUserToAddRows = false;
            queue.AllowUserToDeleteRows = false;
            queue.AllowUserToResizeRows = false;
            queue.ReadOnly = true;
            queue.MultiSelect = true;
            queue.SelectionMode = DataGridViewSelectionMode.FullRowSelect;
            queue.RowHeadersVisible = false;
            queue.AutoSizeRowsMode = DataGridViewAutoSizeRowsMode.None;
            queue.RowTemplate.Height = 34;
            queue.EnableHeadersVisualStyles = false;
            queue.ColumnHeadersHeight = 36;
            queue.ColumnHeadersDefaultCellStyle.BackColor = Color.FromArgb(237, 239, 242);
            queue.ColumnHeadersDefaultCellStyle.ForeColor = Color.FromArgb(55, 61, 68);
            queue.DefaultCellStyle.SelectionBackColor = Color.FromArgb(220, 234, 252);
            queue.DefaultCellStyle.SelectionForeColor = Color.Black;
            queue.DefaultCellStyle.BackColor = Color.White;
            queue.DefaultCellStyle.ForeColor = Color.FromArgb(46, 55, 63);
            queue.AlternatingRowsDefaultCellStyle.BackColor = Color.FromArgb(248, 250, 251);
            queue.AllowDrop = true;

            queue.Columns.Add(new DataGridViewTextBoxColumn
            {
                Name = "FileName",
                HeaderText = "文件",
                AutoSizeMode = DataGridViewAutoSizeColumnMode.Fill,
                FillWeight = 48
            });
            queue.Columns.Add(new DataGridViewTextBoxColumn
            {
                Name = "State",
                HeaderText = "状态",
                Width = 150
            });
            queue.Columns.Add(new DataGridViewTextBoxColumn
            {
                Name = "Result",
                HeaderText = "输出",
                AutoSizeMode = DataGridViewAutoSizeColumnMode.Fill,
                FillWeight = 52
            });

            queue.DragEnter += HandleDragEnter;
            queue.DragDrop += HandleDragDrop;
            queue.Paint += delegate(object sender, PaintEventArgs e)
            {
                if (queue.Rows.Count != 0) return;
                var messageArea = new Rectangle(
                    0,
                    queue.ColumnHeadersHeight + 20,
                    queue.ClientSize.Width,
                    Math.Max(60, queue.ClientSize.Height - queue.ColumnHeadersHeight - 20)
                );
                using (var emptyFont = new Font("Microsoft YaHei UI", 12F, FontStyle.Bold))
                {
                    TextRenderer.DrawText(
                        e.Graphics,
                        "将一个或多个视频拖到这里",
                        emptyFont,
                        messageArea,
                        Color.FromArgb(92, 101, 110),
                        TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter
                    );
                }
            };
            queue.RowsAdded += delegate { queue.Invalidate(); };
            queue.RowsRemoved += delegate { queue.Invalidate(); };
        }

        private static Label CreateFieldLabel(string text)
        {
            return new Label
            {
                Text = text,
                AutoSize = true,
                Anchor = AnchorStyles.Left,
                ForeColor = Color.FromArgb(58, 64, 72),
                Margin = new Padding(0, 0, 8, 0)
            };
        }

        private static Label SectionTitle(string text, Point location)
        {
            return new Label
            {
                Text = text,
                Font = new Font("Microsoft YaHei UI", 10.5F, FontStyle.Bold),
                ForeColor = Color.FromArgb(35, 44, 52),
                AutoSize = true,
                Location = location
            };
        }

        private static Label FieldCaption(string text, Point location)
        {
            return new Label
            {
                Text = text,
                ForeColor = Color.FromArgb(72, 81, 90),
                AutoSize = true,
                Location = location
            };
        }

        private static Button CreateCompactButton(string text, int width)
        {
            var button = new Button
            {
                Text = text,
                Size = new Size(width, 30),
                FlatStyle = FlatStyle.Flat,
                BackColor = Color.White
            };
            button.FlatAppearance.BorderColor = Color.FromArgb(190, 198, 204);
            return button;
        }

        private static void ConfigurePercentInput(NumericUpDown input, decimal value)
        {
            input.Minimum = 0;
            input.Maximum = 100;
            input.Value = value;
            input.Width = 78;
            input.DecimalPlaces = 0;
            input.TextAlign = HorizontalAlignment.Center;
        }

        private static void ConfigureFrameInput(NumericUpDown input, decimal value)
        {
            input.Minimum = 0;
            input.Maximum = 30;
            input.Value = value;
            input.Width = 42;
            input.TextAlign = HorizontalAlignment.Center;
            input.ValueChanged += delegate
            {
                if (input.Focused && input.Parent != null)
                {
                    var form = input.FindForm() as MainForm;
                    if (form != null)
                    {
                        form.cutPreset.SelectedIndex = 3;
                        form.UpdateOptionSummary();
                    }
                }
            };
        }

        private static Button CreateButton(string text)
        {
            var button = new Button
            {
                Text = text,
                Dock = DockStyle.Fill,
                Margin = new Padding(0, 4, 0, 4),
            };
            button.FlatStyle = FlatStyle.Flat;
            button.FlatAppearance.BorderColor = Color.FromArgb(190, 195, 202);
            button.BackColor = Color.White;
            return button;
        }

        private static void StyleCommandButton(Button button, int width)
        {
            button.Width = width;
            button.Height = 34;
            button.Margin = new Padding(6, 0, 0, 0);
            button.FlatStyle = FlatStyle.Flat;
            button.FlatAppearance.BorderColor = Color.FromArgb(190, 195, 202);
            button.BackColor = Color.White;
        }

        private void ConfigureWorker()
        {
            worker.WorkerReportsProgress = true;
            worker.WorkerSupportsCancellation = true;
            worker.DoWork += RunJobs;
            worker.ProgressChanged += ApplyJobUpdate;
            worker.RunWorkerCompleted += FinishJobs;
        }

        private void LoadSettings()
        {
            string defaultAd = Path.Combine(appRoot, "work", "ad-reference.mp4");
            string defaultOutput = Path.Combine(appRoot, "outputs");
            adText.Text = defaultAd;
            outputText.Text = defaultOutput;
            searchMode.SelectedIndex = 0;
            cutPreset.SelectedIndex = 0;

            try
            {
                string readPath = File.Exists(settingsPath) ? settingsPath : legacySettingsPath;
                if (File.Exists(readPath))
                {
                    string[] lines = File.ReadAllLines(readPath, Encoding.UTF8);
                    if (lines.Length > 0 && lines[0].Length > 0) adText.Text = lines[0];
                    if (lines.Length > 1 && lines[1].Length > 0) outputText.Text = lines[1];
                    if (lines.Length > 2) searchMode.SelectedIndex = ParseIndex(lines[2], 0, 2, 0);
                    if (lines.Length > 3) searchStart.Value = ParseDecimal(lines[3], 0, 100, 35);
                    if (lines.Length > 4) searchEnd.Value = ParseDecimal(lines[4], 0, 100, 65);
                    if (lines.Length > 5) leadingGuard.Value = ParseDecimal(lines[5], 0, 30, 3);
                    if (lines.Length > 6) trailingGuard.Value = ParseDecimal(lines[6], 0, 30, 2);
                    if (lines.Length > 7) safetyGuard.Value = ParseDecimal(lines[7], 0, 30, 1);
                    if (lines.Length > 8) cutPreset.SelectedIndex = ParseIndex(lines[8], 0, 3, 3);
                }
            }
            catch
            {
                status.Text = "未能读取上次设置，已使用默认路径。";
            }
            UpdateProfileStatus();
            UpdateOptionSummary();
        }

        private void SaveSettings()
        {
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(settingsPath));
                File.WriteAllLines(
                    settingsPath,
                    new[]
                    {
                        adText.Text.Trim(),
                        outputText.Text.Trim(),
                        searchMode.SelectedIndex.ToString(),
                        searchStart.Value.ToString(),
                        searchEnd.Value.ToString(),
                        leadingGuard.Value.ToString(),
                        trailingGuard.Value.ToString(),
                        safetyGuard.Value.ToString(),
                        cutPreset.SelectedIndex.ToString()
                    },
                    Encoding.UTF8
                );
            }
            catch { }
        }

        private static int ParseIndex(string text, int minimum, int maximum, int fallback)
        {
            int value;
            return Int32.TryParse(text, out value) && value >= minimum && value <= maximum
                ? value
                : fallback;
        }

        private static decimal ParseDecimal(
            string text,
            decimal minimum,
            decimal maximum,
            decimal fallback
        )
        {
            decimal value;
            return Decimal.TryParse(text, out value) && value >= minimum && value <= maximum
                ? value
                : fallback;
        }

        private void SearchModeChanged(object sender, EventArgs e)
        {
            bool custom = searchMode.SelectedIndex == 1;
            searchStart.Visible = custom;
            searchEnd.Visible = custom;
            UpdateOptionSummary();
        }

        private void CutPresetChanged(object sender, EventArgs e)
        {
            if (cutPreset.SelectedIndex == 0)
            {
                SetGuardValues(3, 2, 1);
            }
            else if (cutPreset.SelectedIndex == 1)
            {
                SetGuardValues(1, 1, 0);
            }
            else if (cutPreset.SelectedIndex == 2)
            {
                SetGuardValues(5, 4, 2);
            }
            bool custom = cutPreset.SelectedIndex == 3;
            leadingGuard.Enabled = custom;
            trailingGuard.Enabled = custom;
            safetyGuard.Enabled = custom;
            UpdateOptionSummary();
        }

        private void SetGuardValues(int leading, int trailing, int safety)
        {
            leadingGuard.Value = leading;
            trailingGuard.Value = trailing;
            safetyGuard.Value = safety;
        }

        private void UpdateOptionSummary()
        {
            if (searchMode.SelectedIndex == 2)
            {
                searchRangeLabel.Text = "全片";
            }
            else if (searchMode.SelectedIndex == 1)
            {
                searchRangeLabel.Text = searchStart.Value + "%–" + searchEnd.Value + "%";
            }
            else
            {
                searchRangeLabel.Text = "35%–65%";
            }
            guardSummary.Text = "前 " + leadingGuard.Value + " 帧  ·  后 "
                + trailingGuard.Value + " 帧  ·  安全 " + safetyGuard.Value + " 帧";
        }

        private void UpdateProfileStatus()
        {
            string ad = adText.Text.Trim();
            string profile = Path.ChangeExtension(ad, ".profile.json");
            if (!File.Exists(ad))
            {
                profileStatus.Text = "请先选择或制作广告基准";
                profileStatus.ForeColor = Color.FromArgb(167, 98, 18);
            }
            else if (File.Exists(profile))
            {
                profileStatus.Text = "已加载音频边界校准";
                profileStatus.ForeColor = Color.FromArgb(25, 126, 74);
            }
            else
            {
                profileStatus.Text = "广告基准可用（默认边界）";
                profileStatus.ForeColor = Color.FromArgb(25, 126, 74);
            }
        }

        private void BrowseAd(object sender, EventArgs e)
        {
            using (var dialog = new OpenFileDialog())
            {
                dialog.Title = "选择固定广告基准视频";
                dialog.Filter = "视频文件|*.mp4;*.mkv;*.mov;*.m4v;*.avi|所有文件|*.*";
                dialog.CheckFileExists = true;
                if (File.Exists(adText.Text)) dialog.InitialDirectory = Path.GetDirectoryName(adText.Text);
                if (dialog.ShowDialog(this) == DialogResult.OK)
                {
                    adText.Text = dialog.FileName;
                    SaveSettings();
                }
            }
        }

        private void CreateReference(object sender, EventArgs e)
        {
            string initialDirectory = outputText.Text.Trim();
            if (!Directory.Exists(initialDirectory)) initialDirectory = appRoot;
            using (var dialog = new ReferenceDialog(initialDirectory))
            {
                if (dialog.ShowDialog(this) != DialogResult.OK) return;
                string executable;
                string commandPrefix;
                if (!ResolveRuntime(out executable, out commandPrefix))
                {
                    MessageBox.Show(
                        this,
                        "工具运行文件不完整，无法制作广告基准。",
                        "无法启动",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error
                    );
                    return;
                }

                string arguments = commandPrefix
                    + "prepare-ad --source " + Quote(dialog.SourcePath)
                    + " --start-time " + Decimal.ToDouble(dialog.StartSeconds).ToString(
                        System.Globalization.CultureInfo.InvariantCulture
                    )
                    + " --end-time " + Decimal.ToDouble(dialog.EndSeconds).ToString(
                        System.Globalization.CultureInfo.InvariantCulture
                    )
                    + " --output " + Quote(dialog.OutputPath);
                Cursor previous = Cursor;
                Cursor = Cursors.WaitCursor;
                createReferenceButton.Enabled = false;
                try
                {
                    string output;
                    int exitCode = RunProcess(executable, arguments, out output);
                    if (exitCode != 0 || !File.Exists(dialog.OutputPath))
                    {
                        MessageBox.Show(
                            this,
                            "广告基准生成失败：" + LastUsefulLine(output),
                            "生成失败",
                            MessageBoxButtons.OK,
                            MessageBoxIcon.Error
                        );
                        return;
                    }
                    adText.Text = dialog.OutputPath;
                    SaveSettings();
                    status.Text = "广告基准已生成并自动选中。";
                }
                finally
                {
                    activeProcess = null;
                    createReferenceButton.Enabled = true;
                    Cursor = previous;
                }
            }
        }

        private void BrowseOutput(object sender, EventArgs e)
        {
            using (var dialog = new FolderBrowserDialog())
            {
                dialog.Description = "选择去广告视频的输出目录";
                if (Directory.Exists(outputText.Text)) dialog.SelectedPath = outputText.Text;
                if (dialog.ShowDialog(this) == DialogResult.OK)
                {
                    outputText.Text = dialog.SelectedPath;
                    SaveSettings();
                }
            }
        }

        private void BrowseVideos(object sender, EventArgs e)
        {
            using (var dialog = new OpenFileDialog())
            {
                dialog.Title = "添加待处理视频";
                dialog.Filter = "视频文件|*.mp4;*.mkv;*.mov;*.m4v;*.avi;*.ts;*.mts;*.m2ts|所有文件|*.*";
                dialog.Multiselect = true;
                if (dialog.ShowDialog(this) == DialogResult.OK) AddPaths(dialog.FileNames);
            }
        }

        private void HandleDragEnter(object sender, DragEventArgs e)
        {
            e.Effect = e.Data.GetDataPresent(DataFormats.FileDrop) ? DragDropEffects.Copy : DragDropEffects.None;
        }

        private void HandleDragDrop(object sender, DragEventArgs e)
        {
            var paths = e.Data.GetData(DataFormats.FileDrop) as string[];
            if (paths != null) AddPaths(paths);
        }

        private void AddPaths(IEnumerable<string> paths)
        {
            if (worker.IsBusy) return;
            var candidates = new List<string>();
            foreach (string path in paths)
            {
                if (Directory.Exists(path))
                {
                    foreach (string file in Directory.GetFiles(path)) candidates.Add(file);
                }
                else
                {
                    candidates.Add(path);
                }
            }

            var existing = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (DataGridViewRow row in queue.Rows) existing.Add((string)row.Tag);

            int added = 0;
            foreach (string file in candidates)
            {
                string fullPath;
                try { fullPath = Path.GetFullPath(file); }
                catch { continue; }
                if (!File.Exists(fullPath) || !VideoExtensions.Contains(Path.GetExtension(fullPath))) continue;
                if (existing.Contains(fullPath)) continue;
                int rowIndex = queue.Rows.Add(Path.GetFileName(fullPath), "等待处理", "");
                queue.Rows[rowIndex].Tag = fullPath;
                existing.Add(fullPath);
                added++;
            }
            status.Text = added > 0 ? "已添加 " + added + " 个视频。" : "没有发现可添加的新视频。";
        }

        public void AddInitialFiles(IEnumerable<string> paths)
        {
            AddPaths(paths);
        }

        private void RemoveSelected(object sender, EventArgs e)
        {
            if (worker.IsBusy) return;
            foreach (DataGridViewRow row in queue.SelectedRows) queue.Rows.Remove(row);
        }

        private void StartProcessing(object sender, EventArgs e)
        {
            if (worker.IsBusy) return;
            string ad = adText.Text.Trim();
            string outputDirectory = outputText.Text.Trim();
            string executable;
            string commandPrefix;

            if (!File.Exists(ad))
            {
                MessageBox.Show(this, "请先选择有效的广告基准视频。", "缺少广告基准", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            if (!ResolveRuntime(out executable, out commandPrefix))
            {
                MessageBox.Show(this, "工具运行文件不完整：缺少处理引擎。", "无法启动", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }
            if (queue.Rows.Count == 0)
            {
                MessageBox.Show(this, "请先拖入至少一个待处理视频。", "队列为空", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }

            var options = new ProcessingOptions
            {
                FullScan = searchMode.SelectedIndex == 2,
                SearchStartPercent = searchMode.SelectedIndex == 1 ? searchStart.Value : 35,
                SearchEndPercent = searchMode.SelectedIndex == 1 ? searchEnd.Value : 65,
                LeadingGuardFrames = Decimal.ToInt32(leadingGuard.Value),
                TrailingGuardFrames = Decimal.ToInt32(trailingGuard.Value),
                SafetyGuardFrames = Decimal.ToInt32(safetyGuard.Value)
            };
            if (!options.FullScan && options.SearchStartPercent >= options.SearchEndPercent)
            {
                MessageBox.Show(
                    this,
                    "搜索起点必须小于搜索终点。",
                    "搜索范围无效",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning
                );
                return;
            }

            try { Directory.CreateDirectory(outputDirectory); }
            catch (Exception ex)
            {
                MessageBox.Show(this, "无法创建输出目录：" + ex.Message, "目录错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            SaveSettings();
            var jobs = new List<Job>();
            string recordRoot = Path.Combine(outputDirectory, "_ClipClean处理记录");
            for (int i = 0; i < queue.Rows.Count; i++)
            {
                string input = (string)queue.Rows[i].Tag;
                string stem = Path.GetFileNameWithoutExtension(input);
                jobs.Add(new Job
                {
                    RowIndex = i,
                    Input = input,
                    Output = Path.Combine(outputDirectory, stem + "_已去广告.mp4"),
                    Report = Path.Combine(recordRoot, stem + ".report.json"),
                    PreviewDirectory = Path.Combine(recordRoot, stem + "_边界预览"),
                    Log = Path.Combine(recordRoot, stem + ".log")
                });
                queue.Rows[i].Cells["State"].Value = "等待处理";
                queue.Rows[i].Cells["Result"].Value = "";
            }

            SetBusy(true);
            progress.Minimum = 0;
            progress.Maximum = 100;
            progress.Value = 0;
            status.Text = "正在准备处理…";
            worker.RunWorkerAsync(new object[] { jobs, ad, executable, commandPrefix, options });
        }

        private void RunJobs(object sender, DoWorkEventArgs e)
        {
            object[] arguments = (object[])e.Argument;
            var jobs = (List<Job>)arguments[0];
            string ad = (string)arguments[1];
            string executable = (string)arguments[2];
            string commandPrefix = (string)arguments[3];
            var options = (ProcessingOptions)arguments[4];

            int completed = 0;
            foreach (Job job in jobs)
            {
                if (worker.CancellationPending)
                {
                    e.Cancel = true;
                    return;
                }

                if (File.Exists(job.Output))
                {
                    completed++;
                    worker.ReportProgress(ProgressPercent(completed, jobs.Count), new JobUpdate
                    {
                        RowIndex = job.RowIndex,
                        Status = "已跳过（输出已存在）",
                        Output = job.Output,
                        Detail = "为保护已有文件，未覆盖 " + Path.GetFileName(job.Output)
                    });
                    continue;
                }

                worker.ReportProgress(ProgressPercent(completed, jobs.Count), new JobUpdate
                {
                    RowIndex = job.RowIndex,
                    Status = "正在检测并剪切…",
                    Output = "",
                    Detail = "正在处理 " + Path.GetFileName(job.Input)
                });

                string args = commandPrefix
                    + "cut --ad " + Quote(ad)
                    + " --video " + Quote(job.Input)
                    + " --output " + Quote(job.Output)
                    + " --report " + Quote(job.Report)
                    + " --preview-dir " + Quote(job.PreviewDirectory)
                    + " --mode audio-safe"
                    + " --leading-guard-frames " + options.LeadingGuardFrames
                    + " --trailing-guard-frames " + options.TrailingGuardFrames
                    + " --safety-guard-frames " + options.SafetyGuardFrames;
                if (options.FullScan)
                {
                    args += " --full-scan";
                }
                else
                {
                    args += " --search-start-ratio "
                        + Decimal.ToDouble(options.SearchStartPercent / 100).ToString(
                            System.Globalization.CultureInfo.InvariantCulture
                        );
                    args += " --search-end-ratio "
                        + Decimal.ToDouble(options.SearchEndPercent / 100).ToString(
                            System.Globalization.CultureInfo.InvariantCulture
                        );
                }

                string output;
                int exitCode;
                try
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(job.Report));
                    Directory.CreateDirectory(job.PreviewDirectory);
                    exitCode = RunProcess(executable, args, out output);
                }
                catch (Exception ex)
                {
                    exitCode = -1;
                    output = ex.Message;
                }

                job.Log = WriteProcessingLog(job, ad, executable, args, exitCode, output);

                completed++;
                bool succeeded = exitCode == 0 && File.Exists(job.Output);
                string failureDetail = "处理失败：" + LastUsefulLine(output)
                    + (String.IsNullOrEmpty(job.Log) ? "；日志写入也失败" : "；完整日志：" + job.Log);
                worker.ReportProgress(ProgressPercent(completed, jobs.Count), new JobUpdate
                {
                    RowIndex = job.RowIndex,
                    Status = succeeded ? "处理完成" : "处理失败",
                    Output = succeeded ? job.Output : job.Log,
                    Detail = succeeded
                        ? "已输出 " + Path.GetFileName(job.Output)
                        : failureDetail
                });
            }
        }

        private bool ResolveRuntime(out string executable, out string commandPrefix)
        {
            string packagedEngine = Path.Combine(appRoot, "clipclean-engine.exe");
            if (!File.Exists(packagedEngine))
            {
                packagedEngine = Path.Combine(appRoot, "adskip-engine.exe");
            }
            if (File.Exists(packagedEngine))
            {
                executable = packagedEngine;
                commandPrefix = String.Empty;
                return true;
            }

            string python = Path.Combine(appRoot, ".venv", "Scripts", "python.exe");
            string script = Path.Combine(appRoot, "adskip.py");
            if (File.Exists(python) && File.Exists(script))
            {
                executable = python;
                commandPrefix = "-X utf8 " + Quote(script) + " ";
                return true;
            }

            executable = String.Empty;
            commandPrefix = String.Empty;
            return false;
        }

        private int RunProcess(string executable, string arguments, out string combinedOutput)
        {
            var info = new ProcessStartInfo
            {
                FileName = executable,
                Arguments = arguments,
                WorkingDirectory = appRoot,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8
            };
            info.EnvironmentVariables["PYTHONUTF8"] = "1";
            var log = new StringBuilder();
            using (var process = new Process())
            {
                process.StartInfo = info;
                process.OutputDataReceived += delegate(object sender, DataReceivedEventArgs eventArgs)
                {
                    if (eventArgs.Data != null) lock (log) log.AppendLine(eventArgs.Data);
                };
                process.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs eventArgs)
                {
                    if (eventArgs.Data != null) lock (log) log.AppendLine(eventArgs.Data);
                };
                activeProcess = process;
                process.Start();
                process.BeginOutputReadLine();
                process.BeginErrorReadLine();
                process.WaitForExit();
                process.WaitForExit();
                activeProcess = null;
                combinedOutput = log.ToString();
                return process.ExitCode;
            }
        }

        private void ApplyJobUpdate(object sender, ProgressChangedEventArgs e)
        {
            var update = (JobUpdate)e.UserState;
            if (update.RowIndex >= 0 && update.RowIndex < queue.Rows.Count)
            {
                queue.Rows[update.RowIndex].Cells["State"].Value = update.Status;
                queue.Rows[update.RowIndex].Cells["Result"].Value = update.Output;
                queue.Rows[update.RowIndex].Cells["State"].ToolTipText = update.Detail;
                queue.Rows[update.RowIndex].Cells["Result"].ToolTipText = update.Output;
            }
            progress.Value = Math.Max(progress.Minimum, Math.Min(progress.Maximum, e.ProgressPercentage));
            status.Text = update.Detail;
        }

        private void FinishJobs(object sender, RunWorkerCompletedEventArgs e)
        {
            activeProcess = null;
            SetBusy(false);
            if (e.Cancelled)
            {
                status.Text = "处理已停止；已经生成的文件会保留。";
            }
            else if (e.Error != null)
            {
                status.Text = "处理异常终止：" + e.Error.Message;
                MessageBox.Show(this, e.Error.Message, "处理异常", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            else
            {
                int succeeded = 0;
                int failed = 0;
                int skipped = 0;
                foreach (DataGridViewRow row in queue.Rows)
                {
                    string state = Convert.ToString(row.Cells["State"].Value);
                    if (state == "处理完成") succeeded++;
                    else if (state == "处理失败") failed++;
                    else if (state.StartsWith("已跳过")) skipped++;
                }
                status.Text = "处理结束：成功 " + succeeded + "，失败 " + failed + "，跳过 " + skipped + "。原视频均未修改。";
            }
        }

        private void CancelProcessing(object sender, EventArgs e)
        {
            if (!worker.IsBusy) return;
            worker.CancelAsync();
            status.Text = "正在停止当前任务…";
            try
            {
                Process process = activeProcess;
                if (process != null && !process.HasExited) process.Kill();
            }
            catch { }
        }

        private void HandleFormClosing(object sender, FormClosingEventArgs e)
        {
            if (worker.IsBusy)
            {
                DialogResult choice = MessageBox.Show(
                    this,
                    "当前仍在处理视频。停止任务并退出吗？",
                    "处理尚未结束",
                    MessageBoxButtons.YesNo,
                    MessageBoxIcon.Warning
                );
                if (choice != DialogResult.Yes)
                {
                    e.Cancel = true;
                    return;
                }
                worker.CancelAsync();
                try
                {
                    Process process = activeProcess;
                    if (process != null && !process.HasExited) process.Kill();
                }
                catch { }
            }
            SaveSettings();
        }

        private void SetBusy(bool busy)
        {
            startButton.Enabled = !busy;
            cancelButton.Enabled = busy;
            addButton.Enabled = !busy;
            removeButton.Enabled = !busy;
            clearButton.Enabled = !busy;
            openResultButton.Enabled = !busy;
            createReferenceButton.Enabled = !busy;
            adText.Enabled = !busy;
            outputText.Enabled = !busy;
            searchMode.Enabled = !busy;
            cutPreset.Enabled = !busy;
            bool customSearch = !busy && searchMode.SelectedIndex == 1;
            searchStart.Enabled = customSearch;
            searchEnd.Enabled = customSearch;
            bool customCut = !busy && cutPreset.SelectedIndex == 3;
            leadingGuard.Enabled = customCut;
            trailingGuard.Enabled = customCut;
            safetyGuard.Enabled = customCut;
        }

        private void OpenOutputDirectory(object sender, EventArgs e)
        {
            string directory = outputText.Text.Trim();
            try
            {
                Directory.CreateDirectory(directory);
                Process.Start(new ProcessStartInfo(directory) { UseShellExecute = true });
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, ex.Message, "无法打开目录", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private void OpenSelectedResult(object sender, EventArgs e)
        {
            if (queue.SelectedRows.Count == 0)
            {
                MessageBox.Show(this, "请先选择一条任务。", "没有选择", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            string path = Convert.ToString(queue.SelectedRows[0].Cells["Result"].Value);
            if (!File.Exists(path))
            {
                MessageBox.Show(this, "这条任务还没有可打开的结果或日志。", "暂无结果", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            try
            {
                Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, ex.Message, "无法打开", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private static string Quote(string value)
        {
            return "\"" + value.Replace("\"", "\\\"") + "\"";
        }

        private static string LastUsefulLine(string text)
        {
            if (String.IsNullOrWhiteSpace(text)) return "没有可用的错误信息";
            string[] lines = text.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);
            return lines.Length == 0 ? text.Trim() : lines[lines.Length - 1].Trim();
        }

        private static string BuildLog(
            Job job,
            string ad,
            string executable,
            string arguments,
            int exitCode,
            string output
        )
        {
            var log = new StringBuilder();
            log.AppendLine("ClipClean v" + AppVersion + " processing log");
            log.AppendLine("time: " + DateTimeOffset.Now.ToString("O"));
            log.AppendLine("input: " + job.Input);
            log.AppendLine("ad: " + ad);
            log.AppendLine("output: " + job.Output);
            log.AppendLine("report: " + job.Report);
            log.AppendLine("exit_code: " + exitCode);
            log.AppendLine("command: " + executable + " " + arguments);
            log.AppendLine();
            log.AppendLine(output.Trim());
            return log.ToString();
        }

        private static string WriteProcessingLog(
            Job job,
            string ad,
            string executable,
            string arguments,
            int exitCode,
            string output
        )
        {
            string content = BuildLog(job, ad, executable, arguments, exitCode, output);
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(job.Log));
                File.WriteAllText(job.Log, content, new UTF8Encoding(true));
                return job.Log;
            }
            catch
            {
                try
                {
                    string fallbackDirectory = Path.Combine(
                        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                        "ClipClean",
                        "logs"
                    );
                    Directory.CreateDirectory(fallbackDirectory);
                    string fallback = Path.Combine(
                        fallbackDirectory,
                        Path.GetFileNameWithoutExtension(job.Input)
                            + "-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".log"
                    );
                    File.WriteAllText(fallback, content, new UTF8Encoding(true));
                    return fallback;
                }
                catch
                {
                    return String.Empty;
                }
            }
        }

        private static int ProgressPercent(int completed, int total)
        {
            return total <= 0 ? 0 : (int)Math.Round(completed * 100.0 / total);
        }
    }

    internal static class Program
    {
        [STAThread]
        private static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            string[] args = Environment.GetCommandLineArgs();
            if (args.Length >= 3 && args[1] == "--screenshot-reference")
            {
                using (var dialog = new ReferenceDialog(AppDomain.CurrentDomain.BaseDirectory))
                {
                    dialog.Show();
                    Application.DoEvents();
                    using (var bitmap = new Bitmap(dialog.Width, dialog.Height))
                    {
                        dialog.DrawToBitmap(bitmap, new Rectangle(0, 0, dialog.Width, dialog.Height));
                        bitmap.Save(args[2], System.Drawing.Imaging.ImageFormat.Png);
                    }
                    dialog.Close();
                }
                return;
            }
            if (args.Length >= 3 && args[1] == "--screenshot")
            {
                using (var form = new MainForm())
                {
                    if (args.Length > 3)
                    {
                        var previewFiles = new string[args.Length - 3];
                        Array.Copy(args, 3, previewFiles, 0, previewFiles.Length);
                        form.AddInitialFiles(previewFiles);
                    }
                    form.Show();
                    Application.DoEvents();
                    form.PerformLayout();
                    Application.DoEvents();
                    using (var bitmap = new Bitmap(form.Width, form.Height))
                    {
                        form.DrawToBitmap(bitmap, new Rectangle(0, 0, form.Width, form.Height));
                        bitmap.Save(args[2], System.Drawing.Imaging.ImageFormat.Png);
                    }
                    form.Close();
                }
                return;
            }
            var mainForm = new MainForm();
            if (args.Length > 1)
            {
                var initialFiles = new string[args.Length - 1];
                Array.Copy(args, 1, initialFiles, 0, initialFiles.Length);
                mainForm.AddInitialFiles(initialFiles);
            }
            Application.Run(mainForm);
        }
    }
}
