using PacketProcessing.Entities;
using QuestDB.Senders;
using Xunit;

namespace PacketProcessing.Tests.unit;

public class EntityTests
{
    [Fact]
    public void MotionPacketEntity_TableName_IsCorrect()
    {
        var entity = new MotionPacketEntity
        {
            Type = true,
            OpCode = "TEST",
            OpCodeDescription = "Test Description",
            Axis = 1,
            FloatValue = 1.5f,
            Timestamp = DateTime.UtcNow
        };
        
        Assert.Equal("motion_packets", entity.TableName);
    }
    
    [Fact]
    public void OnVIFPacketEntity_TableName_IsCorrect()
    {
        var entity = new OnVIFPacketEntity
        {
            Type = true,
            Description = "Test Description",
            Zoom = 2.0f,
            Measurement = 10.5f,
            Timestamp = DateTime.UtcNow
        };
        
        Assert.Equal("onvif_packets", entity.TableName);
    }
    
    [Fact]
    public void SafetyPacketEntity_TableName_IsCorrect()
    {
        var entity = new SafetyPacketEntity
        {
            Type = true,
            OpCode = "SAFETY",
            OpCodeDescription = "Safety Test",
            State = "ACTIVE",
            Timestamp = DateTime.UtcNow
        };
        
        Assert.Equal("safety_packets", entity.TableName);
    }
    
    [Fact]
    public void MotionPacketEntity_WriteColumns_DoesNotThrow()
    {
        var entity = new MotionPacketEntity
        {
            Type = true,
            OpCode = "TEST",
            OpCodeDescription = "Test Description",
            Axis = 1,
            FloatValue = 1.5f,
            Timestamp = DateTime.UtcNow
        };
        
        // This should not throw an exception
        Assert.Null(Record.Exception(() => entity.WriteColumns(null)));
    }
    
    [Fact]
    public void OnVIFPacketEntity_WriteColumns_DoesNotThrow()
    {
        var entity = new OnVIFPacketEntity
        {
            Type = true,
            Description = "Test Description",
            Zoom = 2.0f,
            Measurement = 10.5f,
            Timestamp = DateTime.UtcNow
        };
        
        // This should not throw an exception
        Assert.Null(Record.Exception(() => entity.WriteColumns(null)));
    }
    
    [Fact]
    public void SafetyPacketEntity_WriteColumns_DoesNotThrow()
    {
        var entity = new SafetyPacketEntity
        {
            Type = true,
            OpCode = "SAFETY",
            OpCodeDescription = "Safety Test",
            State = "ACTIVE",
            Timestamp = DateTime.UtcNow
        };
        
        // This should not throw an exception
        Assert.Null(Record.Exception(() => entity.WriteColumns(null)));
    }
    
    [Fact]
    public void MotionPacketEntity_ToRowMap_ReturnsValidRowMap()
    {
        var entity = new MotionPacketEntity
        {
            Type = true,
            OpCode = "TEST",
            OpCodeDescription = "Test Description",
            Axis = 1,
            FloatValue = 1.5f,
            Timestamp = DateTime.UtcNow
        };
        
        var rowMap = entity.ToRowMap();
        
        Assert.NotNull(rowMap);
        Assert.Equal("motion_packets", rowMap.Table);
    }
    
    [Fact]
    public void OnVIFPacketEntity_ToRowMap_ReturnsValidRowMap()
    {
        var entity = new OnVIFPacketEntity
        {
            Type = true,
            Description = "Test Description",
            Zoom = 2.0f,
            Measurement = 10.5f,
            Timestamp = DateTime.UtcNow
        };
        
        var rowMap = entity.ToRowMap();
        
        Assert.NotNull(rowMap);
        Assert.Equal("onvif_packets", rowMap.Table);
    }
    
    [Fact]
    public void SafetyPacketEntity_ToRowMap_ReturnsValidRowMap()
    {
        var entity = new SafetyPacketEntity
        {
            Type = true,
            OpCode = "SAFETY",
            OpCodeDescription = "Safety Test",
            State = "ACTIVE",
            Timestamp = DateTime.UtcNow
        };
        
        var rowMap = entity.ToRowMap();
        
        Assert.NotNull(rowMap);
        Assert.Equal("safety_packets", rowMap.Table);
    }
}
