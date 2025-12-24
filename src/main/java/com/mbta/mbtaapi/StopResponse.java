package com.mbta.mbtaapi;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public class StopResponse {
    public List<StopData> data;

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class StopData {
        public String id;
        public StopAttributes attributes;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class StopAttributes {
        public String name;
    }
}
