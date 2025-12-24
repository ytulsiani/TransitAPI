package com.mbta.mbtaapi;

public class StopSummary {
    public String id;
    public String name;

    public StopSummary() {}

    public StopSummary(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public static StopSummary fromStopData(StopResponse.StopData stopData) {
        if (stopData == null) {
            return new StopSummary();
        }

        String name = stopData.attributes != null ? stopData.attributes.name : null;

        return new StopSummary(stopData.id, name);
    }
}
