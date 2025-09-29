// 全局变量
let socket = null;
let temperatureChart = null;
let levelChart = null;
let chartData = {
    labels: [],
    // 为每个罐创建单独的温度和液位数据集
    temperatureDatasets: [],
    levelDatasets: []
};
const MAX_CHART_POINTS = 30; // 图表最大点数
let alarmModal = null;
let lastUpdateTime = new Date();
let processedTanks = new Set(); // 用于跟踪已处理的罐
let tankColors = []; // 存储每个罐的颜色

// DOM加载完成后执行
$(document).ready(function() {
    // 初始化警报模态框
    alarmModal = new bootstrap.Modal(document.getElementById('alarm-modal'));
    
    // 仅在未禁用Socket.IO时初始化连接
    if (!window.appConfig || !window.appConfig.disableSocketIO) {
        initSocket();
    } else {
        console.log('Socket.IO已禁用');
        // 模拟Socket.IO连接断开的状态
        updateMQTTStatus(false, 'Socket.IO已禁用');
        // 设置定时刷新数据
        setInterval(fetchDataPeriodically, 30000); // 每30秒刷新一次数据
        // 立即获取一次数据
        fetchDataPeriodically();
    }
    
    // 初始化图表
    initCharts();
    
    // 初始化时间显示
    updateTime();
    setInterval(updateTime, 1000);
    
    // 初始化存储设置
    initStorageSettings();
    
    // 初始化历史数据查询功能
    initHistoryQuery();
    
    // 绑定误差更新按钮事件
    $('.update-error-btn').on('click', function() {
        const tankId = $(this).data('tank-id');
        updateTankError(tankId);
    });
    
    // 绑定MQTT连接按钮事件
    $('#connect-mqtt-btn').on('click', function() {
        connectMQTT();
    });
    
    // 绑定MQTT订阅按钮事件
    $('#subscribe-btn').on('click', function() {
        subscribeTopic();
    });
    
    // 绑定MQTT发布按钮事件
    $('#publish-btn').on('click', function() {
        publishMessage();
    });
    
    // 绑定回车键事件
    $('.error-input').on('keypress', function(e) {
        if (e.which === 13) {
            const tankId = $(this).attr('id').split('-')[1];
            updateTankError(tankId);
        }
    });
    
    // 添加滚动监听，实现导航栏高亮
    $(window).scroll(function() {
        highlightNavigation();
    });
    
    // 初始化时高亮导航
    highlightNavigation();
});

// 初始化Socket.IO连接
function initSocket() {
    // 获取当前页面的URL
    const url = window.location.origin;
    
    // 创建Socket.IO连接
    socket = io(url);
    
    // 连接成功事件
    socket.on('connect', function() {
        console.log('WebSocket连接成功');
    });
    
    // 断开连接事件
    socket.on('disconnect', function() {
        console.log('WebSocket连接断开');
        updateMQTTStatus(false);
    });
    
    // MQTT状态更新事件
    socket.on('mqtt_status', function(data) {
        updateMQTTStatus(data.connected, data.message);
    });
    
    // 罐数据更新事件
    socket.on('tank_data_update', function(data) {
        updateTankData(data);
        updateLastUpdateTime();
    });
    
    // 警报事件
    socket.on('alarm', function(data) {
        showAlarm(data);
    });
    
    // MQTT消息事件
    socket.on('mqtt_message', function(data) {
        console.log('收到MQTT消息:', data);
    });
    
    // 订阅状态事件
    socket.on('subscription_status', function(data) {
        showNotification(data.message, data.success ? 'success' : 'error');
    });
    
    // 发布状态事件
    socket.on('publish_status', function(data) {
        showNotification(data.message, data.success ? 'success' : 'error');
    });
}

// 定期从API获取数据（当Socket.IO被禁用时使用）
function fetchDataPeriodically() {
    $.ajax({
        url: '/api/tanks/data',
        type: 'GET',
        dataType: 'json',
        success: function(response) {
            if (response.success && response.data) {
                updateTankData(response.data);
                updateLastUpdateTime();
            }
        },
        error: function(xhr, status, error) {
            console.error('获取数据失败:', error);
        }
    });
}

// 更新MQTT连接状态
function updateMQTTStatus(connected, message = '') {
    const statusElement = $('#mqtt-status');
    
    if (connected) {
        statusElement.removeClass('bg-danger').addClass('bg-success');
        statusElement.html('<i class="fa fa-check-circle" aria-hidden="true"></i> MQTT 已连接' + (message ? ' - ' + message : ''));
    } else {
        statusElement.removeClass('bg-success').addClass('bg-danger');
        statusElement.html('<i class="fa fa-exclamation-circle" aria-hidden="true"></i> MQTT 未连接' + (message ? ' - ' + message : ''));
    }
}

// 更新罐数据显示
function updateTankData(tanks) {
    let totalTemperature = 0;
    let totalLevel = 0;
    let totalWeight = 0;
    let alarmCount = 0;
    let tankCount = 0;
    
    // 更新每个罐的数据
    $.each(tanks, function(tankId, tank) {
        tankId = parseInt(tankId);
        
        // 更新温度显示
        $(`#temp-${tankId}`).text(`${tank.temperature.toFixed(1)} °C`);
        
        // 更新液位显示 - 直接使用原始液位值，不再加上误差
        $(`#level-value-${tankId}`).text(tank.level.toFixed(3) + " m");
        
        // 更新吨位显示
        $(`#weight-${tankId}`).text(tank.weight.toFixed(3) + " t");
        
        // 更新高限显示
        const highLimitElement = $(`.tank-card[data-tank-id="${tankId}"] .high-limit`);
        if (highLimitElement.length > 0) {
            highLimitElement.text(`${tank.high_limit.toFixed(3)} m`);
        }
        
        // 更新液位可视化
        const levelPercentage = (tank.level / tank.height) * 100;
        $(`#level-${tankId}`).css('height', `${Math.min(levelPercentage, 100)}%`);
        
        // 更新高限线位置
        const highLimitLine = $(`.tank-card[data-tank-id="${tankId}"] .high-limit-line`);
        if (highLimitLine.length > 0) {
            const highLimitPercentage = (tank.high_limit / tank.height) * 100;
            highLimitLine.css('bottom', `${highLimitPercentage}%`);
        }
        
        // 更新罐状态
        const statusElement = $(`#status-${tankId}`);
        if (tank.alarm_shown) {
            statusElement.removeClass('bg-success').addClass('bg-danger alarm');
            statusElement.text('警报');
            alarmCount++;
        } else {
            statusElement.removeClass('bg-danger alarm').addClass('bg-success');
            statusElement.text('正常');
        }
        
        // 累积统计数据
        totalTemperature += tank.temperature;
        totalLevel += tank.level;
        totalWeight += tank.weight;
        tankCount++;
        
        // 更新图表数据
        updateChartData(tankId, tank);
    });
    
    // 更新统计信息
    if (tankCount > 0) {
        $(`#avg-temperature`).text(`${(totalTemperature / tankCount).toFixed(1)} °C`);
        $(`#avg-level`).text(`${(totalLevel / tankCount).toFixed(2)} m`);
        $(`#total-weight`).text(`${totalWeight.toFixed(1)} t`);
        $(`#alarm-count`).text(alarmCount);
    }
    
    // 更新图表
    updateCharts();
}

// 更新图表数据 - 修改为处理每个罐的单独数据集
function updateChartData(tankId, tank) {
    const now = new Date();
    const timeStr = now.toLocaleTimeString();
    
    // 如果这是新的时间点，添加到标签中
    if (chartData.labels.length === 0 || chartData.labels[chartData.labels.length - 1] !== timeStr) {
        chartData.labels.push(timeStr);
        
        // 保持图表点数不超过最大值
        if (chartData.labels.length > MAX_CHART_POINTS) {
            chartData.labels.shift();
            
            // 移除所有数据集的第一个数据点
            chartData.temperatureDatasets.forEach(dataset => {
                if (dataset.data.length > 0) {
                    dataset.data.shift();
                }
            });
            chartData.levelDatasets.forEach(dataset => {
                if (dataset.data.length > 0) {
                    dataset.data.shift();
                }
            });
        }
    }
    
    // 如果这是第一次处理这个罐，为其创建数据集
    if (!processedTanks.has(tankId)) {
        processedTanks.add(tankId);
        
        // 生成随机颜色
        const color = generateColor(tankId);
        tankColors[tankId] = color;
        
        // 创建温度数据集
        chartData.temperatureDatasets.push({
            label: `罐 ${tankId} 温度`,
            data: new Array(chartData.labels.length).fill(null), // 初始化为null
            borderColor: color,
            backgroundColor: `${color}33`, // 透明度33
            borderWidth: 2,
            tension: 0.1,
            fill: false,
            pointRadius: 3,
            pointHoverRadius: 5
        });
        
        // 创建液位数据集
        chartData.levelDatasets.push({
            label: `罐 ${tankId} 液位`,
            data: new Array(chartData.labels.length).fill(null), // 初始化为null
            borderColor: color,
            backgroundColor: `${color}33`, // 透明度33
            borderWidth: 2,
            tension: 0.1,
            fill: false,
            pointRadius: 3,
            pointHoverRadius: 5
        });
    }
    
    // 找到这个罐的数据集索引
    const tankIndex = Array.from(processedTanks).indexOf(tankId);
    
    // 更新数据点
    if (tankIndex !== -1) {
        // 如果这是新的时间点，添加新数据点；否则更新最后一个数据点
        if (chartData.labels[chartData.labels.length - 1] === timeStr) {
            chartData.temperatureDatasets[tankIndex].data[chartData.labels.length - 1] = tank.temperature;
            chartData.levelDatasets[tankIndex].data[chartData.labels.length - 1] = tank.level;
        }
    }
}

// 初始化图表
function initCharts() {
    // 温度图表
    const temperatureCtx = document.getElementById('temperature-chart').getContext('2d');
    temperatureChart = new Chart(temperatureCtx, {
        type: 'line',
        data: {
            labels: chartData.labels,
            datasets: chartData.temperatureDatasets
        },
        options: getChartOptions('温度趋势')
    });
    
    // 液位图表
    const levelCtx = document.getElementById('level-chart').getContext('2d');
    levelChart = new Chart(levelCtx, {
        type: 'line',
        data: {
            labels: chartData.labels,
            datasets: chartData.levelDatasets
        },
        options: getChartOptions('液位趋势')
    });
}

// 获取图表通用配置
function getChartOptions(title) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            title: {
                display: false
            },
            legend: {
                position: 'top',
            },
            tooltip: {
                mode: 'index',
                intersect: false,
            }
        },
        scales: {
            x: {
                grid: {
                    display: false
                }
            },
            y: {
                beginAtZero: false,
                grid: {
                    color: 'rgba(0, 0, 0, 0.05)'
                }
            }
        },
        interaction: {
            mode: 'nearest',
            axis: 'x',
            intersect: false
        }
    };
}

// 更新图表显示
function updateCharts() {
    if (temperatureChart && levelChart) {
        temperatureChart.data.labels = chartData.labels;
        temperatureChart.data.datasets = chartData.temperatureDatasets;
        temperatureChart.update();
        
        levelChart.data.labels = chartData.labels;
        levelChart.data.datasets = chartData.levelDatasets;
        levelChart.update();
    }
}

// 生成基于罐ID的颜色
function generateColor(tankId) {
    // 预定义一些不同的颜色
    const colors = [
        '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF',
        '#FF9F40', '#8AC926', '#1982C4', '#6A4C93', '#F45B69',
        '#C5D86D', '#3185FC', '#F7B801', '#7B2CBF', '#F94144'
    ];
    
    // 使用罐ID对颜色数组长度取模，确保每个罐有一个固定的颜色
    return colors[tankId % colors.length];
}

// 显示警报
function showAlarm(data) {
    const message = `罐 ${data.tank_name} 的液位(${data.level.toFixed(3)} m)超过高限(${data.high_limit.toFixed(1)} m)！`;
    $('#alarm-message').text(message);
    alarmModal.show();
    
    // 添加声音提醒（可选）
    // playAlarmSound();
}

// 更新罐误差值
function updateTankError(tankId) {
    const errorInput = $(`#error-${tankId}`);
    const errorValue = parseFloat(errorInput.val());
    const tankHeight = parseFloat(errorInput.attr('data-tank-height'));
    
    // 验证输入
    if (isNaN(errorValue)) {
        showNotification('请输入有效的误差值', 'error');
        return;
    }
    
    if (errorValue < -tankHeight || errorValue > tankHeight) {
        showNotification(`误差值必须在-${tankHeight}到+${tankHeight}之间`, 'error');
        return;
    }
    
    // 保留3位小数
    const roundedErrorValue = Math.round(errorValue * 1000) / 1000;
    
    // 发送请求更新误差值
    $.ajax({
        url: `/api/tank/${tankId}/error`,
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ error: roundedErrorValue }),
        success: function(response) {
            showNotification(response.message, 'success');
            // 更新输入框显示的值为3位小数
            errorInput.val(roundedErrorValue.toFixed(3));
        },
        error: function(xhr) {
            let message = '更新失败';
            if (xhr.responseJSON && xhr.responseJSON.message) {
                message = xhr.responseJSON.message;
            }
            showNotification(message, 'error');
        }
    });
}

// 连接MQTT服务器（前端触发的连接，实际连接逻辑在后端）
function connectMQTT() {
    const broker = $('#mqtt-broker').val();
    const port = $('#mqtt-port').val();
    const useTls = $('#use-tls').prop('checked');
    
    // 验证输入
    if (!broker || !port) {
        showNotification('请填写MQTT服务器地址和端口', 'error');
        return;
    }
    
    // 显示连接中状态
    $('#mqtt-status').html('<i class="fa fa-spinner fa-spin" aria-hidden="true"></i> 连接中...');
    
    // 注意：实际的MQTT连接逻辑在后端，这里只是重新加载页面来应用新的配置
    // 在实际应用中，可以通过API请求让后端重新连接
    location.reload();
}

// 订阅MQTT主题
function subscribeTopic() {
    const topic = $('#subscribe-topic').val().trim();
    
    if (!topic) {
        showNotification('请输入要订阅的主题', 'error');
        return;
    }
    
    // 通过Socket.IO发送订阅请求
    socket.emit('subscribe_topic', { topic: topic, qos: 1 });
}

// 发布MQTT消息
function publishMessage() {
    const topic = $('#publish-topic').val().trim();
    const message = $('#publish-message').val().trim();
    
    if (!topic) {
        showNotification('请输入要发布的主题', 'error');
        return;
    }
    
    if (!message) {
        showNotification('请输入要发布的消息', 'error');
        return;
    }
    
    // 尝试解析消息为JSON
    let payload = message;
    try {
        payload = JSON.parse(message);
    } catch (e) {
        // 如果不是有效的JSON，保持原样
    }
    
    // 通过Socket.IO发送发布请求
    socket.emit('publish_message', { 
        topic: topic, 
        payload: payload, 
        qos: 1,
        retain: false 
    });
}

// 显示通知
function showNotification(message, type = 'info') {
    // 创建通知元素
    const notification = $(`<div class="toast fade show position-fixed top-0 end-0 m-3" role="alert" aria-live="assertive" aria-atomic="true">
        <div class="toast-header">
            <i class="mr-2"></i>
            <strong class="mr-auto"></strong>
            <button type="button" class="ml-2 mb-1 close" data-dismiss="toast" aria-label="Close">
                <span aria-hidden="true">&times;</span>
            </button>
        </div>
        <div class="toast-body"></div>
    </div>`);
    
    // 设置通知样式和内容
    const icon = notification.find('i');
    const title = notification.find('strong');
    const body = notification.find('.toast-body');
    
    if (type === 'success') {
        notification.addClass('bg-success text-white');
        icon.addClass('fa fa-check-circle');
        title.text('成功');
    } else if (type === 'error') {
        notification.addClass('bg-danger text-white');
        icon.addClass('fa fa-exclamation-circle');
        title.text('错误');
    } else {
        notification.addClass('bg-info text-white');
        icon.addClass('fa fa-info-circle');
        title.text('信息');
    }
    
    body.text(message);
    
    // 添加到页面并自动移除
    $('body').append(notification);
    
    setTimeout(function() {
        notification.toast('hide');
        notification.on('hidden.bs.toast', function() {
            notification.remove();
        });
    }, 3000);
}

// 更新当前时间
function updateTime() {
    const now = new Date();
    const timeStr = now.toLocaleTimeString();
    $('#current-time').text(timeStr);
}

// 更新最后更新时间
function updateLastUpdateTime() {
    const now = new Date();
    const timeStr = now.toLocaleTimeString();
    $('#update-time').text(`最后更新: ${timeStr}`);
}

// 高亮导航栏
function highlightNavigation() {
    const scrollPosition = $(window).scrollTop();
    
    // 获取所有部分的位置
    const sections = ['#dashboard', '#charts', '#settings', '#about'];
    
    for (let i = sections.length - 1; i >= 0; i--) {
        const section = $(sections[i]);
        if (section.length && section.offset().top - 100 <= scrollPosition) {
            // 移除所有激活状态
            $('.nav-link').removeClass('active');
            // 添加当前部分的激活状态
            $(`.nav-link[href="${sections[i]}"]`).addClass('active');
            break;
        }
    }
}

// 播放警报声音（可选）
function playAlarmSound() {
    try {
        const audio = new Audio('/static/sounds/alarm.mp3');
        audio.play();
    } catch (e) {
        console.error('播放警报声音失败:', e);
    }
}

// 页面卸载时断开Socket.IO连接
    $(window).on('beforeunload', function() {
        if (socket) {
            socket.disconnect();
        }
    });

// 初始化存储设置
function initStorageSettings() {
    // 获取当前存储设置
    $.ajax({
        url: '/api/storage/days',
        type: 'GET',
        success: function(response) {
            $('#current-storage-days').text(response.storage_days);
            $('#storage-days').val(response.storage_days);
        },
        error: function(xhr) {
            console.error('获取存储天数失败:', xhr);
        }
    });
    
    // 获取当前历史数据点数量设置
    $.ajax({
        url: '/api/history/points',
        type: 'GET',
        success: function(response) {
            $('#current-history-points').text(response.history_points);
            $('#history-points').val(response.history_points);
        },
        error: function(xhr) {
            console.error('获取历史数据点数量失败:', xhr);
        }
    });
    
    // 绑定保存设置按钮事件
    $('#save-storage-settings-btn').on('click', function() {
        const days = parseInt($('#storage-days').val());
        const points = parseInt($('#history-points').val());
        
        // 验证输入
        if (isNaN(days) || days < 1 || days > 365) {
            showNotification('请输入1-365之间的有效天数', 'error');
            return;
        }
        
        if (isNaN(points) || points < 100 || points > 100000) {
            showNotification('请输入100-100000之间的有效数据点数量', 'error');
            return;
        }
        
        // 先保存存储天数
        $.ajax({
            url: '/api/storage/days',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ days: days }),
            success: function(storageResponse) {
                // 再保存历史数据点数量
                $.ajax({
                    url: '/api/history/points',
                    type: 'POST',
                    contentType: 'application/json',
                    data: JSON.stringify({ points: points }),
                    success: function(pointsResponse) {
                        if (storageResponse.success && pointsResponse.success) {
                            $('#current-storage-days').text(storageResponse.storage_days);
                            $('#current-history-points').text(pointsResponse.history_points);
                            $('#storage-settings-status').html('<div class="alert alert-success">存储设置已保存</div>');
                            setTimeout(function() {
                                $('#storage-settings-status').empty();
                            }, 3000);
                        } else {
                            $('#storage-settings-status').html('<div class="alert alert-warning">部分设置保存失败，请重试</div>');
                        }
                    },
                    error: function(xhr) {
                        console.error('保存历史数据点数量失败:', xhr);
                        $('#storage-settings-status').html('<div class="alert alert-warning">存储天数已保存，但历史数据点数量保存失败</div>');
                    }
                });
            },
            error: function(xhr) {
                console.error('保存存储天数失败:', xhr);
                $('#storage-settings-status').html('<div class="alert alert-danger">保存失败</div>');
            }
        });
    });
}

// 初始化历史数据查询功能
function initHistoryQuery() {
    // 设置默认日期为最近7天
    const today = new Date();
    const sevenDaysAgo = new Date(today);
    sevenDaysAgo.setDate(today.getDate() - 7);
    
    $('#history-end-date').val(formatDate(today));
    $('#history-start-date').val(formatDate(sevenDaysAgo));
    
    // 默认勾选显示实时数据
    $('#show-real-time').prop('checked', true);
    
    // 绑定查询按钮事件
    $('#query-history-btn').on('click', function() {
        queryHistoryData();
    });
}

// 格式化日期为YYYY-MM-DD格式
function formatDate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

// 查询历史数据
function queryHistoryData() {
    console.log('查询历史数据函数被调用');
    const tankId = $('#history-tank-select').val();
    console.log('选择的罐ID:', tankId);
    const startDate = $('#history-start-date').val();
    const endDate = $('#history-end-date').val();
    const showRealTime = $('#show-real-time').is(':checked');
    
    // 验证输入
    if (!tankId) {
        console.log('未选择罐');
        showNotification('请选择要查询的罐', 'error');
        return;
    }
    
    if (!startDate || !endDate) {
        console.log('日期选择不完整');
        showNotification('请选择开始日期和结束日期', 'error');
        return;
    }
    
    if (new Date(startDate) > new Date(endDate)) {
        console.log('日期顺序错误');
        showNotification('开始日期不能晚于结束日期', 'error');
        return;
    }
    
    // 显示加载状态
    showNotification('正在查询历史数据...', 'info');
    console.log('开始查询历史数据:', { tankId, startDate, endDate, showRealTime });
    
    // 如果选择了特定的罐
    if (tankId !== 'all') {
        console.log('查询单个罐数据');
        // 使用新的显示函数
        displaySingleTankHistory(tankId, startDate, endDate, showRealTime);
    } else {
        console.log('查询所有罐数据');
        // 如果选择了所有罐，获取所有罐的历史数据
        getAllTanksHistory(startDate, endDate, showRealTime);
    }
}

// 获取单个罐的历史数据 - 返回Promise对象
function getSingleTankHistory(tankId, startDate, endDate) {
    console.log('准备发送AJAX请求获取历史数据:', { tankId, startDate, endDate });
    return new Promise((resolve, reject) => {
        // 确保tankId是字符串格式，并移除可能的空格或特殊字符
        tankId = String(tankId).trim();
        console.log('转换后的tankId:', tankId, '类型:', typeof tankId);
        
        // 转换日期为ISO格式
        const startDateTime = new Date(startDate).toISOString();
        const endDateTime = new Date(new Date(endDate).setHours(23, 59, 59, 999)).toISOString();
        
        // 构建完整的URL以便调试
        const requestUrl = `/api/history/${encodeURIComponent(tankId)}`;
        console.log('完整请求URL:', requestUrl);
        
        // 显示加载状态
        showNotification(`正在获取罐 ${tankId} 的历史数据...`, 'info');
        
        $.ajax({
            url: requestUrl,
            type: 'GET',
            data: {
                start_time: startDateTime,
                end_time: endDateTime
            },
            dataType: 'json',
            beforeSend: function() {
                console.log('正在发送AJAX请求...');
            },
            success: function(response) {
                console.log('AJAX请求成功，响应:', response);
                if (response.success && response.history) {
                    console.log('历史数据数量:', response.history.length);
                    resolve(response.history);
                } else {
                    showNotification('未找到历史数据', 'info');
                    resolve([]);
                }
            },
            error: function(xhr) {
                console.error('获取历史数据失败:', xhr);
                console.error('错误详情:', xhr);
                console.error('响应文本:', xhr.responseText);
                console.error('状态码:', xhr.status);
                showNotification('获取历史数据失败，错误码: ' + xhr.status, 'error');
                reject(xhr);
            },
            complete: function(xhr, status) {
                console.log('AJAX请求完成，状态:', status);
                console.log('响应状态码:', xhr.status);
            }
        });
    });
}

// 用于直接显示单个罐历史数据的包装函数
function displaySingleTankHistory(tankId, startDate, endDate, showRealTime) {
    console.log('开始获取单个罐历史数据:', { tankId, startDate, endDate });
    getSingleTankHistory(tankId, startDate, endDate)
        .then(historyData => {
            console.log('获取单个罐历史数据成功，数据量:', historyData.length);
            displayHistoryData(tankId, historyData, showRealTime);
        })
        .catch(error => {
            console.error('获取历史数据失败:', error);
        });
}

// 获取所有罐的历史数据
function getAllTanksHistory(startDate, endDate, showRealTime) {
    // 获取所有罐ID
    const tankIds = [];
    $('.tank-card').each(function() {
        tankIds.push($(this).data('tank-id'));
    });
    
    // 存储每个罐的历史数据
    const allHistoryData = {};
    let completedRequests = 0;
    
    // 为每个罐获取历史数据
    tankIds.forEach(tankId => {
        getSingleTankHistory(tankId, startDate, endDate).then(historyData => {
            allHistoryData[tankId] = historyData;
            completedRequests++;
            
            // 当所有请求完成后，显示数据
            if (completedRequests === tankIds.length) {
                displayAllTanksHistory(allHistoryData, showRealTime);
            }
        }).catch(error => {
            console.error(`获取罐 ${tankId} 历史数据失败:`, error);
            completedRequests++;
        });
    });
}

// 显示单个罐的历史数据
function displayHistoryData(tankId, historyData, showRealTime) {
    console.log('开始显示单个罐历史数据:', { tankId, dataCount: historyData.length });
    
    // 准备图表数据
    const labels = historyData.map(item => {
        const date = new Date(item.timestamp);
        return date.toLocaleString();
    });
    
    console.log('准备图表标签数量:', labels.length);
    
    // 保存当前的实时数据（如果需要恢复）
    const currentChartData = {
        labels: [...chartData.labels],
        temperatureDatasets: JSON.parse(JSON.stringify(chartData.temperatureDatasets)),
        levelDatasets: JSON.parse(JSON.stringify(chartData.levelDatasets))
    };
    
    // 清空当前图表数据
    chartData.labels = labels;
    chartData.temperatureDatasets = [];
    chartData.levelDatasets = [];
    
    console.log('清空当前图表数据完成');
    
    // 创建温度数据集
    chartData.temperatureDatasets.push({
        label: `罐 ${tankId} 温度`,
        data: historyData.map(item => item.temperature),
        borderColor: tankColors[tankId] || generateColor(tankId),
        backgroundColor: `${tankColors[tankId] || generateColor(tankId)}33`,
        borderWidth: 2,
        tension: 0.1,
        fill: false,
        pointRadius: 3,
        pointHoverRadius: 5
    });
    
    // 创建液位数据集
    chartData.levelDatasets.push({
        label: `罐 ${tankId} 液位`,
        data: historyData.map(item => item.level),
        borderColor: tankColors[tankId] || generateColor(tankId),
        backgroundColor: `${tankColors[tankId] || generateColor(tankId)}33`,
        borderWidth: 2,
        tension: 0.1,
        fill: false,
        pointRadius: 3,
        pointHoverRadius: 5
    });
    
    console.log('创建温度/液位数据集完成');
    
    // 更新图表
    updateCharts();
    console.log('图表更新完成');
    
    // 如果需要保持显示实时数据，设置一个恢复函数
    if (showRealTime) {
        // 用户可能会在查看历史数据后，希望返回到实时数据视图
        // 这里可以添加一个按钮或其他UI元素来触发返回实时数据的操作
        showNotification('历史数据已显示，新的实时数据仍会继续更新', 'success');
        
        // 30秒后自动恢复到实时数据视图
        setTimeout(() => {
            if (confirm('是否返回实时数据视图？')) {
                chartData = currentChartData;
                updateCharts();
            }
        }, 30000);
    } else {
        showNotification('已切换到历史数据视图', 'success');
    }
}

// 显示所有罐的历史数据
function displayAllTanksHistory(allHistoryData, showRealTime) {
    // 保存当前的实时数据（如果需要恢复）
    const currentChartData = {
        labels: [...chartData.labels],
        temperatureDatasets: JSON.parse(JSON.stringify(chartData.temperatureDatasets)),
        levelDatasets: JSON.parse(JSON.stringify(chartData.levelDatasets))
    };
    
    // 清空当前图表数据
    chartData.labels = [];
    chartData.temperatureDatasets = [];
    chartData.levelDatasets = [];
    
    // 为每个罐创建数据集
    let hasData = false;
    Object.keys(allHistoryData).forEach(tankId => {
        const historyData = allHistoryData[tankId];
        if (historyData && historyData.length > 0) {
            hasData = true;
            
            // 如果标签为空，使用当前罐的时间标签
            if (chartData.labels.length === 0) {
                chartData.labels = historyData.map(item => {
                    const date = new Date(item.timestamp);
                    return date.toLocaleString();
                });
            }
            
            // 创建温度数据集
            chartData.temperatureDatasets.push({
                label: `罐 ${tankId} 温度`,
                data: historyData.map(item => item.temperature),
                borderColor: tankColors[tankId] || generateColor(tankId),
                backgroundColor: `${tankColors[tankId] || generateColor(tankId)}33`,
                borderWidth: 2,
                tension: 0.1,
                fill: false,
                pointRadius: 3,
                pointHoverRadius: 5
            });
            
            // 创建液位数据集
            chartData.levelDatasets.push({
                label: `罐 ${tankId} 液位`,
                data: historyData.map(item => item.level),
                borderColor: tankColors[tankId] || generateColor(tankId),
                backgroundColor: `${tankColors[tankId] || generateColor(tankId)}33`,
                borderWidth: 2,
                tension: 0.1,
                fill: false,
                pointRadius: 3,
                pointHoverRadius: 5
            });
        }
    });
    
    // 更新图表
    updateCharts();
    
    // 显示通知
    if (hasData) {
        showNotification('已显示所有罐的历史数据', 'success');
        
        // 如果需要保持显示实时数据，设置一个恢复函数
        if (showRealTime) {
            // 30秒后自动提示是否返回实时数据视图
            setTimeout(() => {
                if (confirm('是否返回实时数据视图？')) {
                    chartData = currentChartData;
                    updateCharts();
                }
            }, 30000);
        }
    } else {
        showNotification('未找到任何罐的历史数据', 'info');
    }
}